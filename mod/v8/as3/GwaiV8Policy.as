// Final consolidated response-v8 guards, in reference priority order.
// Operates only on detached own/public state. Runtime execution is separate.
internal class GwaiV8Policy
{
    public static function choose(state:Object,context:Object,level:int = 2):Object
    { return GwaiV8Policy.guards(state,context,GwaiV8Response.choose(state,context,level)); }
    public static function finish(base:Object,move:Object,reason:String = null,passValue:Boolean = false):Object
    {
        var out:Object = GwaiV8Position.copyMap(base); out.action = move; out.revision = "response-v8";
        if(reason != null) out.reason = reason;
        if(passValue) out.value = base.pass_value;
        return out;
    }
    public static function projectionFailure(error:Error):Boolean
    {
        return error is GwaiV8Unsupported || ["illegal projected leader action","illegal projected card action","chain on non-Medic","empty graveyard chain","illegal recovery"].indexOf(error.message) >= 0;
    }
    public static function spy(card:Object):Boolean
    { return GwaiV8Position.isType(card,256) || GwaiV8Position.has(card,34); }
    public static function boardSpies(state:Object):Array
    {
        var out:Array = [];
        for(var loc:String in state.board)
        {
            var pair:Array = loc.split(":"); if(int(pair[0]) != state.player) continue;
            var list:Array = state.board[loc];
            for(var i:int = 0; i < list.length; ++i)
                if(GwaiV8Policy.spy(state.cards[list[i]]) && !GwaiV8Position.isType(state.cards[list[i]],128)) out.push(list[i]);
        }
        return out;
    }
    public static function bestKey(state:Object,keys:Array,maximum:Boolean = false):int
    {
        var best:int = keys[0];
        for(var i:int = 1; i < keys.length; ++i)
        {
            var key:int = keys[i]; var power:Number = state.cards[key].power; var bestPower:Number = state.cards[best].power;
            if(maximum ? power > bestPower || (power == bestPower && key > best) : power < bestPower || (power == bestPower && key < best)) best = key;
        }
        return best;
    }
    public static function firstRow(card:Object):int
    {
        for(var i:int = 0; i < GwaiV8Position.ROWS.length; ++i)
        { var row:int = GwaiV8Position.ROWS[i]; if(GwaiV8Position.isType(card,GwaiV8Position.rowFlag(row))) return row; }
        return 5;
    }
    public static function medicChain(state:Object,eligible:Array,bestSpy:int):Array
    {
        var medics:Array = [];
        for(var i:int = 0; i < eligible.length; ++i)
        {
            var key:int = eligible[i]; var card:Object = state.cards[key];
            if(key != bestSpy && GwaiV8Position.has(card,33) && !GwaiV8Position.isType(card,128)) medics.push(key);
        }
        var chain:Array = [];
        if(medics.length > 0)
        { var best:int = GwaiV8Policy.bestKey(state,medics,true); chain.push([best,GwaiV8Policy.firstRow(state.cards[best])]); }
        chain.push([bestSpy,GwaiV8Policy.firstRow(state.cards[bestSpy])]); return chain;
    }
    public static function winningCostOrder(a:Object,b:Object):Number
    {
        if(a.cost != b.cost) return a.cost-b.cost;
        if(a.negative_gain != b.negative_gain) return a.negative_gain-b.negative_gain;
        if(a.move.source != b.move.source) return a.move.source-b.move.source;
        return a.order-b.order;
    }
    // Single non-spy plays after which the round is ours, cheapest first ({cost, negative_gain, move});
    // same as response_v8.securing_plays (Blunder Fix #2, and overkill-trim against a passed opponent).
    public static function securingPlays(state:Object,context:Object):Array
    {
        var own:int = state.player; var other:int = 1-own; var scores:Array = state.scores();
        var ties:Boolean = GwaiV8Sequence.winsTies(context) || GwaiV8Response.tieMatch(context);
        var candidates:Array = []; var initial:Number = state.reserve(); var moves:Array = state.actions();
        for(var i:int = 0; i < moves.length; ++i)
        {
            var card:Object = state.cards[moves[i].source]; if(card == null || GwaiV8Position.isType(card,256)) continue;
            try
            {
                var after:Object = state.apply(moves[i]); var sc:Array = after.scores();
                if(sc[own] > sc[other] || (sc[own] == sc[other] && ties))
                    candidates.push({cost:initial-after.reserve(),negative_gain:-((sc[own]-sc[other])-(scores[own]-scores[other])),move:moves[i],order:candidates.length});
            }
            catch(error:Error) { if(!GwaiV8Policy.projectionFailure(error)) throw error; }
        }
        candidates.sort(winningCostOrder); return candidates;
    }
    // The V8 guards, then the shipped NPC rules (same order as response_v8.choose_response_v8).
    public static function guards(state:Object,context:Object,base:Object):Object
    { return GwaiV8Policy.rules(state,context,GwaiV8Policy.fixes(state,context,base)); }
    public static function fixes(state:Object,context:Object,base:Object):Object
    {
        var move:Object = base.action; var card:Object; var after:Object; var safe:Boolean = false; var i:int; var key:int;
        var secure:Boolean = GwaiV8Response.secured(state,context);
        if(context.opponent_passed && move != null && secure)
        {
            card = state.cards[move.source];
            if(card != null && GwaiV8Position.isType(card,256))
                try { after = state.apply(move); safe = after.unknown_draws > state.unknown_draws && GwaiV8Response.secured(after,context); }
                catch(error:Error) { if(!GwaiV8Policy.projectionFailure(error)) throw error; }
            if(!safe) return GwaiV8Policy.finish(base,null,"pass_for_match_resources",true);
        }
        var scores:Array; var own:int = state.player; var other:int = 1-own;
        var ties:Boolean = GwaiV8Sequence.winsTies(context) || GwaiV8Response.tieMatch(context);
        if(context.opponent_passed && (move == null || ["pass_for_match_resources","proven_no_supported_overtake"].indexOf(base.reason) >= 0) && !secure)
        {
            var candidates:Array = GwaiV8Policy.securingPlays(state,context);
            if(candidates.length > 0 && (context.opponent_losses >= 1 || context.round_index >= 2 || context.own_losses >= 1 || (context.round_index == 0 && state.hand.length >= 2)))
                return GwaiV8Policy.finish(base,candidates[0].move,"overtake_passed_opponent_win");
        }
        if(context.opponent_passed && move != null && !secure && context.own_losses == 0 && context.round_index < 2)
        {
            var bounds:Array = GwaiV8Sequence.bounds(state);
            if(bounds != null && (ties ? bounds[0] < bounds[1] : bounds[0] <= bounds[1]))
                return GwaiV8Policy.finish(base,null,"concede_unwinnable_chase",true);
        }
        var targets:Array; var bestSpy:int; var newMove:Object;
        if(!context.opponent_passed && context.own_losses == 0)
        {
            var decoys:Array = [];
            for(i = 0; i < state.hand.length; ++i) if(GwaiV8Position.has(state.cards[state.hand[i]],26)) decoys.push(state.hand[i]);
            if(decoys.length > 0)
            {
                targets = GwaiV8Policy.boardSpies(state);
                if(targets.length > 0 && !(move != null && targets.indexOf(move.target) >= 0))
                { bestSpy = GwaiV8Policy.bestKey(state,targets); return GwaiV8Policy.finish(base,GwaiV8Position.action(decoys[0],-1,bestSpy),"proactive_decoy_spy"); }
            }
        }
        if(move != null)
        {
            card = state.cards[move.source];
            if(card != null && GwaiV8Position.has(card,26) && move.target != -1)
            {
                var target:Object = state.cards[move.target];
                if(target != null && !GwaiV8Policy.spy(target))
                {
                    targets = GwaiV8Policy.boardSpies(state);
                    if(targets.length > 0)
                    { newMove = GwaiV8Position.copyMap(move); newMove.target = GwaiV8Policy.bestKey(state,targets); return GwaiV8Policy.finish(base,newMove,"decoy_spy_retarget"); }
                }
            }
        }
        var eligible:Array = state.recoveryTargets(own); var graveSpies:Array = [];
        for(i = 0; i < eligible.length; ++i)
        { key = eligible[i]; if(GwaiV8Policy.spy(state.cards[key]) && !GwaiV8Position.isType(state.cards[key],128)) graveSpies.push(key); }
        if(move != null && graveSpies.length > 0)
        {
            card = state.cards[move.source];
            if(card != null && GwaiV8Position.has(card,33))
            {
                var chain:Array = move.chain == null ? [] : move.chain; var hasSpy:Boolean = false;
                for(i = 0; i < chain.length; ++i) hasSpy = hasSpy || GwaiV8Policy.spy(state.cards[chain[i][0]]);
                if(!hasSpy)
                {
                    safe = context.own_losses == 0; bestSpy = GwaiV8Policy.bestKey(state,graveSpies);
                    // Last card in hand (same rule as response_v8.py): prefer the spy's two draws.
                    var deckLeft:int = -int(state.unknown_draws); for(var countKey:String in state.counts) deckLeft += int(state.counts[countKey]);
                    if(!safe && !context.opponent_passed && state.hand.length == 1 && deckLeft >= 2) safe = true;
                    if(!safe && context.opponent_passed)
                    { scores = state.scores(); if(scores[own]-scores[other] > state.cards[bestSpy].power) safe = true; }
                    if(safe)
                    { newMove = GwaiV8Position.copyMap(move); newMove.chain = GwaiV8Policy.medicChain(state,eligible,bestSpy); return GwaiV8Policy.finish(base,newMove,"medic_spy_retarget"); }
                }
            }
        }
        if(move == null && !context.opponent_passed && context.own_losses == 0 && graveSpies.length > 0)
        {
            var medics:Array = [];
            for(i = 0; i < state.hand.length; ++i)
            { key = state.hand[i]; if(GwaiV8Position.has(state.cards[key],33) && state.supported(state.cards[key])) medics.push(key); }
            if(medics.length > 0)
            {
                var bestMedic:int = GwaiV8Policy.bestKey(state,medics); bestSpy = GwaiV8Policy.bestKey(state,graveSpies);
                return GwaiV8Policy.finish(base,GwaiV8Position.action(bestMedic,GwaiV8Policy.firstRow(state.cards[bestMedic]),-1,GwaiV8Policy.medicChain(state,eligible,bestSpy)),"proactive_medic_spy");
            }
        }
        // Blunder Fix #6 (same rule as response_v8.py): no wasted card/leader before the opponent passes.
        if(!context.opponent_passed && move != null && GwaiV8Policy.wastedMove(state,move))
        {
            var options:Array = base.alternatives == null ? [] : base.alternatives;
            for(i = 0; i < options.length; ++i)
            {
                var option:Object = options[i].action;
                if(!GwaiV8Policy.sameMove(option,move) && !GwaiV8Policy.wastedMove(state,option))
                {
                    var replaced:Object = GwaiV8Policy.finish(base,option,"avoid_wasted_resource");
                    replaced.value = options[i].oneTurnValue; return replaced;
                }
            }
            // Also pass after a lost round when nothing would be left in hand, or when the
            // search values passing above the wasted move (same rule as response_v8.py).
            var emptyAfter:Boolean = true; var hand:Array = state.hand;
            for(i = 0; i < hand.length; ++i) if(hand[i] != move.source) { emptyAfter = false; break; }
            if(context.own_losses == 0 || emptyAfter || base.pass_value > base.value) return GwaiV8Policy.finish(base,null,"pass_for_match_resources",true);
        }
        return GwaiV8Policy.finish(base,move);
    }
    public static function sameMove(a:Object,b:Object):Boolean
    {
        if(a.source != b.source || int(a.slot) != int(b.slot) || int(a.target) != int(b.target)) return false;
        var ca:Array = a.chain == null ? [] : a.chain; var cb:Array = b.chain == null ? [] : b.chain;
        if(ca.length != cb.length) return false;
        for(var i:int = 0; i < ca.length; ++i) if(ca[i][0] != cb[i][0] || ca[i][1] != cb[i][1]) return false;
        return true;
    }
    // Two narrow blunders (same as response_v8.wasted_move): weather that costs us more than the
    // opponent right now, and a Horn (card or leader) that adds nothing on an empty row.
    public static function wastedMove(state:Object,move:Object):Boolean
    {
        var kinds:Array = GwaiV8Policy.weatherOrHorn(state,move); var weather:Boolean = kinds[0];
        if(!weather && !kinds[1]) return false;
        var gain:Number = GwaiV8Policy.scoreGain(state,move); if(isNaN(gain)) return false;
        return weather ? gain < 0 : gain <= 0;
    }
    // [weather, horn] (response_v8.weather_or_horn): a weather card or leader "pick weather", a Horn card or leader Horn.
    public static function weatherOrHorn(state:Object,move:Object):Array
    {
        var card:Object = state.cards[move.source]; if(card == null) return [false,false];
        var own:int = state.player; var leader:Boolean = state.leaders != null && move.source == state.leaders[own];
        var effect:int = leader ? int(state.leaderEffect(own)) : -1;
        var weather:Boolean = (!leader && GwaiV8Position.isType(card,16) && !GwaiV8Position.has(card,30)) || [12,13,11,10].indexOf(effect) >= 0;
        var horn:Boolean = (!leader && GwaiV8Position.isType(card,64) && GwaiV8Position.has(card,27)) || [18,19,20].indexOf(effect) >= 0;
        return [weather,horn];
    }
    // Change of our score lead made by the move now; NaN when it cannot be projected (response_v8.score_gain).
    public static function scoreGain(state:Object,move:Object):Number
    {
        var after:Object;
        try { after = state.apply(move); }
        catch(error:Error) { if(!GwaiV8Policy.projectionFailure(error)) throw error; return NaN; }
        var own:int = state.player; var other:int = 1-own; var before:Array = state.scores(); var later:Array = after.scores();
        return (later[own]-later[other])-(before[own]-before[other]);
    }

    // ---- Shipped NPC rules from in-game matches g152-g157 (same as response_v8.npc_switches with
    // weather-guard, medic-hold, overkill-trim and agile-dry, in that order; the Lab-only switches
    // are not in the game). ----
    // Moves of earlier fixes that the rules leave alone (only agile-dry may still move their row).
    public static var PROTECTED:Array = ["proactive_decoy_spy","decoy_spy_retarget","medic_spy_retarget","proactive_medic_spy"];
    public static function rules(state:Object,context:Object,result:Object):Object
    {
        var move:Object = result.action; if(move == null) return result;
        var found:Object;
        if(GwaiV8Policy.PROTECTED.indexOf(result.reason) < 0)
        {
            // weather-guard: no weather that gains nothing now, no unit into our own weather.
            if(GwaiV8Policy.uselessWeather(state,context,move))
            {
                found = GwaiV8Policy.replacement(state,context,result,false,0);
                if(found != null) return GwaiV8Policy.rules(state,context,GwaiV8Policy.replaced(result,found,"weather_guard"));
            }
            if(GwaiV8Policy.wetUnit(state,move))
            {
                found = GwaiV8Policy.replacement(state,context,result,true,GwaiV8Policy.ownValue(result));
                if(found != null) return GwaiV8Policy.rules(state,context,GwaiV8Policy.replaced(result,found,"weather_guard_dry_unit"));
            }
            // medic-hold: keep a Medic until the graveyard holds a unit to revive.
            if(GwaiV8Policy.emptyMedic(state,context,move))
            {
                found = GwaiV8Policy.replacement(state,context,result,false,0);
                if(found != null) return GwaiV8Policy.rules(state,context,GwaiV8Policy.replaced(result,found,"medic_hold"));
            }
            // overkill-trim: win the round with the smallest commitment.
            if(result.reason != "overkill_trim")
            {
                var trimmed:Object = GwaiV8Policy.overkillTrim(state,context,result);
                if(trimmed != null) return GwaiV8Policy.rules(state,context,trimmed);
            }
        }
        // agile-dry: an agile unit goes to its dry row unless the weathered one is strictly better now.
        var moved:Object = GwaiV8Policy.dryRows(state,move);
        if(moved != null)
        {
            var wet:Number = GwaiV8Policy.scoreGain(state,move); var dry:Number = GwaiV8Policy.scoreGain(state,moved);
            if(!isNaN(wet) && !isNaN(dry) && dry >= wet) return GwaiV8Policy.finish(result,moved,"agile_dry");
        }
        return result;
    }
    // overkill-trim (response_v8.overkill_trim): when the round is won or being won, the cheapest play
    // that keeps it. Opponent passed: the cheapest securing play replaces a dearer one. Opponent still
    // playing, we lead and a later round exists: the searched non-spy unit from the hand valued above
    // passing, that keeps the lead and that no rule vetoes, costing the least reserve.
    public static function overkillTrim(state:Object,context:Object,result:Object):Object
    {
        var move:Object = result.action; var card:Object = state.cards[move.source];
        if(card != null && GwaiV8Position.isType(card,256)) return null;
        var chosen:Number = GwaiV8Policy.commitment(state,move); if(isNaN(chosen)) return null;
        if(context.opponent_passed)
        {
            var plays:Array = GwaiV8Policy.securingPlays(state,context);
            if(plays.length > 0 && plays[0].cost < chosen-1e-9) return GwaiV8Policy.finish(result,plays[0].move,"overkill_trim");
            return null;
        }
        if(context.round_index >= 2 || (context.own_losses > 0 && context.opponent_losses > 0) || !GwaiV8Response.secured(state,context)) return null;
        var options:Array = result.alternatives == null ? [] : result.alternatives; var best:Object = null;
        for(var i:int = 0; i < options.length; ++i)
        {
            var option:Object = options[i].action; var value:Number = options[i].oneTurnValue;
            var unit:Object = GwaiV8Policy.inHandCard(state,option);
            if(GwaiV8Policy.sameMove(option,move) || unit == null || !GwaiV8Position.isType(unit,8) || GwaiV8Position.isType(unit,256)
                || value <= result.pass_value || GwaiV8Policy.vetoed(state,context,option)) continue;
            var cost:Number = GwaiV8Policy.commitment(state,option);
            if(isNaN(cost) || cost >= chosen-1e-9) continue;
            var keeps:Boolean = false;
            try { keeps = GwaiV8Response.secured(state.apply(option),context); }
            catch(error:Error) { if(!GwaiV8Policy.projectionFailure(error)) throw error; }
            if(keeps && (best == null || cost < best.cost || (cost == best.cost && value > best.value))) best = {cost:cost,value:value,option:options[i]};
        }
        return best == null ? null : GwaiV8Policy.replaced(result,best.option,"overkill_trim");
    }
    // Reserve the move spends (our hand's worth for later rounds); NaN when it cannot be projected.
    public static function commitment(state:Object,move:Object):Number
    {
        try { return state.reserve()-state.apply(move).reserve(); }
        catch(error:Error) { if(!GwaiV8Policy.projectionFailure(error)) throw error; }
        return NaN;
    }
    public static function replaced(result:Object,option:Object,reason:String):Object
    { var out:Object = GwaiV8Policy.finish(result,option.action,reason); out.value = option.oneTurnValue; return out; }
    // Best searched alternative, in the search's own order, that no rule vetoes (response_v8.replacement);
    // dryOnly: only a non-hero unit from the hand, not into our weather, valued at least `floor`.
    public static function replacement(state:Object,context:Object,result:Object,dryOnly:Boolean,floor:Number):Object
    {
        var options:Array = result.alternatives == null ? [] : result.alternatives;
        for(var i:int = 0; i < options.length; ++i)
        {
            var option:Object = options[i].action;
            if(GwaiV8Policy.sameMove(option,result.action)) continue;
            if(dryOnly)
            {
                var card:Object = GwaiV8Policy.inHandCard(state,option);
                if(!(options[i].oneTurnValue >= floor && card != null && GwaiV8Position.isType(card,8)
                    && !GwaiV8Position.isType(card,128) && !GwaiV8Policy.wetUnit(state,option))) continue;
            }
            if(!GwaiV8Policy.vetoed(state,context,option)) return options[i];
        }
        return null;
    }
    public static function ownValue(result:Object):Number
    {
        var options:Array = result.alternatives == null ? [] : result.alternatives;
        for(var i:int = 0; i < options.length; ++i)
            if(GwaiV8Policy.sameMove(options[i].action,result.action)) return options[i].oneTurnValue;
        return result.value;
    }
    public static function vetoed(state:Object,context:Object,move:Object):Boolean
    {
        return GwaiV8Policy.uselessWeather(state,context,move) || GwaiV8Policy.wetUnit(state,move)
            || GwaiV8Policy.emptyMedic(state,context,move) || GwaiV8Policy.wastedMove(state,move);
    }
    // The hand card a move plays (null for the leader).
    public static function inHandCard(state:Object,move:Object):Object
    {
        if((state.leaders != null && move.source == state.leaders[state.player]) || state.hand.indexOf(move.source) < 0) return null;
        var card:Object = state.cards[move.source]; return card == null ? null : card;
    }
    public static function weathered(state:Object,side:int,row:int):Boolean
    {
        var list:Array = state.effects[GwaiV8Position.slot(side,row)]; if(list == null) return false;
        for(var i:int = 0; i < list.length; ++i) if(GwaiV8Position.isType(state.cards[list[i]],16)) return true;
        return false;
    }
    // weather-guard: a weather play (card or leader pick) whose swing now is not positive.
    public static function uselessWeather(state:Object,context:Object,move:Object):Boolean
    {
        if(context.opponent_passed || !GwaiV8Policy.weatherOrHorn(state,move)[0]) return false;
        var gain:Number = GwaiV8Policy.scoreGain(state,move); return !isNaN(gain) && gain <= 0;
    }
    // weather-guard: a non-hero unit placed into our own row under weather, where it loses power.
    public static function wetUnit(state:Object,move:Object):Boolean
    {
        var card:Object = GwaiV8Policy.inHandCard(state,move); var row:int = int(move.slot);
        if(card == null || !GwaiV8Position.isType(card,8) || GwaiV8Position.isType(card,128) || GwaiV8Position.isType(card,256)
            || GwaiV8Position.ROWS.indexOf(row) < 0) return false;
        return GwaiV8Policy.weathered(state,state.player,row) && card.power > (state.half_weather[state.player] ? 0 : 1);
    }
    // medic-hold: a Medic (unit or hero) with no unit to revive, outside the final round.
    public static function emptyMedic(state:Object,context:Object,move:Object):Boolean
    {
        var card:Object = GwaiV8Policy.inHandCard(state,move);
        if(card == null || !GwaiV8Position.has(card,33) || state.recoveryTargets(state.player).length > 0) return false;
        return !(context.round_index >= 2 || (context.own_losses > 0 && context.opponent_losses > 0));
    }
    // agile-dry: the same play with every agile unit it places (the card and its Medic chain) moved
    // from a row under weather to its other row when that one is dry; null if nothing moves.
    public static function dryRows(state:Object,move:Object):Object
    {
        var card:Object = GwaiV8Policy.inHandCard(state,move);
        if(card == null || !GwaiV8Position.isType(card,8) || GwaiV8Position.isType(card,256)) return null;
        var slot:int = GwaiV8Policy.dryRow(state,move.source,int(move.slot)); var changed:Boolean = slot != int(move.slot);
        var source:Array = move.chain == null ? [] : move.chain; var chain:Array = [];
        for(var i:int = 0; i < source.length; ++i)
        {
            var row:int = GwaiV8Policy.dryRow(state,source[i][0],int(source[i][1]));
            if(row != int(source[i][1])) changed = true;
            chain.push([source[i][0],row]);
        }
        if(!changed) return null;
        var out:Object = GwaiV8Position.copyMap(move); out.slot = slot; out.chain = chain; return out;
    }
    public static function dryRow(state:Object,key:int,row:int):int
    {
        var own:int = state.player;
        if((row == 4 || row == 5) && state.agileUnit(key) && GwaiV8Policy.weathered(state,own,row) && !GwaiV8Policy.weathered(state,own,9-row)) return 9-row;
        return row;
    }
}
