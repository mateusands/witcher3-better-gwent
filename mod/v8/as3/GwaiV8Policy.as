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
    public static function guards(state:Object,context:Object,base:Object):Object
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
            scores = state.scores(); var candidates:Array = []; var initial:Number = state.reserve(); var moves:Array = state.actions();
            for(i = 0; i < moves.length; ++i)
            {
                card = state.cards[moves[i].source]; if(card == null || GwaiV8Position.isType(card,256)) continue;
                try
                {
                    after = state.apply(moves[i]); var sc:Array = after.scores();
                    if(sc[own] > sc[other] || (sc[own] == sc[other] && ties))
                        candidates.push({cost:initial-after.reserve(),negative_gain:-((sc[own]-sc[other])-(scores[own]-scores[other])),move:moves[i],order:candidates.length});
                }
                catch(error:Error) { if(!GwaiV8Policy.projectionFailure(error)) throw error; }
            }
            if(candidates.length > 0 && (context.opponent_losses >= 1 || context.round_index >= 2 || context.own_losses >= 1 || (context.round_index == 0 && state.hand.length >= 2)))
            { candidates.sort(winningCostOrder); return GwaiV8Policy.finish(base,candidates[0].move,"overtake_passed_opponent_win"); }
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
            if(context.own_losses == 0) return GwaiV8Policy.finish(base,null,"pass_for_match_resources",true);
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
        var card:Object = state.cards[move.source]; if(card == null) return false;
        var own:int = state.player; var leader:Boolean = state.leaders != null && move.source == state.leaders[own];
        var effect:int = leader ? int(state.leaderEffect(own)) : -1;
        var weather:Boolean = (!leader && GwaiV8Position.isType(card,16) && !GwaiV8Position.has(card,30)) || [12,13,11,10].indexOf(effect) >= 0;
        var horn:Boolean = (!leader && GwaiV8Position.isType(card,64) && GwaiV8Position.has(card,27)) || [18,19,20].indexOf(effect) >= 0;
        if(!weather && !horn) return false;
        var after:Object;
        try { after = state.apply(move); }
        catch(error:Error) { if(!GwaiV8Policy.projectionFailure(error)) throw error; return false; }
        var other:int = 1-own; var before:Array = state.scores(); var later:Array = after.scores();
        var gain:Number = (later[own]-later[other])-(before[own]-before[other]);
        return weather ? gain < 0 : gain <= 0;
    }
}
