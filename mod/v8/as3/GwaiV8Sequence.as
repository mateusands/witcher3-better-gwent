// Complete deterministic own-action search stage from sequence_search.py.
// Public heuristics are not calibrated win probabilities. Replan each real turn.
internal class GwaiV8Sequence
{
    public static function winsTies(context:Object):Boolean
    { return context.own_faction == 2 && context.opponent_faction != 2; }
    public static function sigmoid(x:Number):Number
    { return 1/(1+Math.exp(-Math.max(-30,Math.min(30,x)))); }
    public static function opponentAverage(state:Object):Number
    {
        var total:Number = 24; var count:int = 4;
        for(var key:String in state.cards)
        {
            var card:Object = state.cards[key];
            if(card.owner == 1-state.player && card.player == 1-state.player && [5,4,3,2].indexOf(card.row) >= 0 && GwaiV8Position.isType(card,8))
            { total += card.power; ++count; }
        }
        return total/count;
    }
    public static function factionCarry(state:Object,side:int,faction:int,nextRound:int):Number
    {
        if(faction != 1 && !(faction == 5 && nextRound == 2)) return 0;
        var keys:Array = faction == 5 ? state.grave[side].slice() : [];
        for(var r:int = 0; r < 3; ++r) keys = keys.concat(state.board[GwaiV8Position.slot(side,GwaiV8Position.ROWS[r])]);
        var total:Number = 0; var count:int = 0;
        for(var i:int = 0; i < keys.length; ++i)
        {
            var card:Object = state.cards[keys[i]];
            if(GwaiV8Position.isType(card,8) && !GwaiV8Position.isType(card,128))
            { ++count; total += faction == 5 && GwaiV8Position.isType(card,256) ? -card.power : card.power; }
        }
        return count == 0 ? 0 : total/count*(faction == 5 ? Math.min(2,count) : 1);
    }
    public static function utility(state:Object,context:Object,depth:int,reserve:Number,mean:Number,passing:Boolean = false,enemyReserve:Object = null):Number
    {
        var own:int = state.player; var other:int = 1-own; var scores:Array = state.scores();
        var replies:int = context.opponent_passed ? 0 : Math.max(0,depth-1);
        var count:int = Math.max(0,context.opponent_hand_count-replies);
        var gap:Number = scores[own]-scores[other]-replies*mean;
        var opposing:Number = (enemyReserve == null ? count*mean : Number(enemyReserve))+(context.opponent_leader_available ? 3 : 0);
        var scale:Number = 4+Math.sqrt(Math.max(1,count))*2;
        var tiedMatchWin:Boolean = gap == 0 && context.opponent_losses >= 1 && context.own_losses == 0 && !(context.opponent_faction == 2 && context.own_faction != 2);
        var wins:Boolean = GwaiV8Sequence.winsTies(context) ? gap >= 0 : gap > 0;
        if(context.opponent_passed && tiedMatchWin) return 1;
        if(state.hand.length == 0 && state.unknown_draws == 0 && !context.own_leader_available && !state.leaderModeled(own)) passing = true;
        var prospect:Number;
        if(context.opponent_passed) prospect = wins ? 1 : 0;
        else if(passing) prospect = wins ? GwaiV8Sequence.sigmoid((gap-opposing)/scale) : 0;
        else prospect = GwaiV8Sequence.sigmoid((gap+(reserve-opposing)*0.25)/scale);
        var ordinaryTie:Boolean = context.own_faction == context.opponent_faction || (context.own_faction != 2 && context.opponent_faction != 2);
        if((context.opponent_losses >= 1 && context.own_losses >= 1) || context.round_index == 2)
        {
            if(context.opponent_passed && gap == 0 && ordinaryTie) return 0.5;
            return prospect;
        }
        var nextRound:int = context.round_index+1;
        var ownFuture:Number = reserve+GwaiV8Sequence.factionCarry(state,own,context.own_faction,nextRound);
        var enemyFuture:Number = opposing+GwaiV8Sequence.factionCarry(state,other,context.opponent_faction,nextRound);
        var ownDraw:Number = 0; var remaining:int = 0; var printed:Number = 0;
        for(var key:String in state.counts)
        { remaining += state.counts[key]; printed += state.catalog[key].power*state.counts[key]; }
        if(context.own_faction == 3 && remaining != 0) ownDraw = printed/remaining;
        var enemyDraw:Number = context.opponent_faction == 3 ? mean : 0;
        if(context.opponent_passed && gap == 0 && context.own_losses == 0 && context.opponent_losses == 0 && ordinaryTie)
            return GwaiV8Sequence.sigmoid((ownFuture-enemyFuture)/scale);
        var leading:Number = GwaiV8Sequence.sigmoid((ownFuture+ownDraw-enemyFuture+mean)/scale);
        var trailing:Number = GwaiV8Sequence.sigmoid((ownFuture-enemyFuture-enemyDraw-mean)/scale);
        if(context.opponent_losses >= 1) return prospect+(1-prospect)*leading;
        if(context.own_losses >= 1) return prospect*leading;
        return prospect*leading+(1-prospect)*trailing;
    }
    public static function bounds(state:Object):Array
    {
        var own:int = state.player; var other:int = 1-own;
        var hand:Array = []; var roster:Array = []; var decoy:Boolean = false; var i:int; var j:int; var r:int; var card:Object;
        for(i = 0; i < state.hand.length; ++i)
        {
            card = state.cards[state.hand[i]];
            if(!state.supported(card) || GwaiV8Position.has(card,34)) return null;
            hand.push(card); decoy = decoy || GwaiV8Position.has(card,26);
        }
        for(r = 0; r < 3; ++r)
        {
            var list:Array = state.board[GwaiV8Position.slot(own,GwaiV8Position.ROWS[r])];
            for(i = 0; i < list.length; ++i) roster.push(state.cards[list[i]]);
        }
        roster = roster.concat(hand); var unitMap:Object = {}; var templates:Object = {};
        for(i = 0; i < roster.length; ++i)
        {
            card = roster[i]; if(decoy && GwaiV8Position.has(card,34)) return null;
            if(GwaiV8Position.isType(card,8)) unitMap[card.key] = card;
        }
        var key:String;
        for(key in unitMap)
            if(GwaiV8Position.has(unitMap[key],31))
                for(j = 0; j < unitMap[key].targets.length; ++j) templates[unitMap[key].targets[j]] = true;
        for(key in templates)
        {
            card = state.catalog[key]; if(!state.supported(card) || GwaiV8Position.has(card,34)) return null;
            for(i = 0; i < int(state.counts[key]); ++i)
            {
                var copy:Object = GwaiV8Position.copyMap(card); copy.key = -(int(key)*10000+i+1); unitMap[copy.key] = copy;
            }
        }
        var units:Array = []; var external:Array = [];
        for(key in unitMap)
        {
            card = unitMap[key];
            if(GwaiV8Position.has(card,40) || GwaiV8Position.has(card,41) || GwaiV8Position.has(card,42)) return null;
            if(decoy && !state.supported(card)) return null;
            units.push(card);
        }
        for(r = 0; r < 3; ++r)
        {
            list = state.effects[GwaiV8Position.slot(own,GwaiV8Position.ROWS[r])];
            for(i = 0; i < list.length; ++i) if(unitMap[list[i]] == null) external.push(state.cards[list[i]]);
        }
        var horn:Boolean = false; var all:Array = roster.concat(external);
        for(i = 0; i < all.length; ++i)
            if(GwaiV8Position.has(all[i],27) || GwaiV8Position.has(all[i],18) || GwaiV8Position.has(all[i],19) || GwaiV8Position.has(all[i],20)) horn = true;
        var ceiling:Number = 0; var moraleRoster:Array = units.concat(external);
        for(i = 0; i < units.length; ++i)
        {
            card = units[i]; if(GwaiV8Position.isType(card,128)) { ceiling += card.power; continue; }
            var bonds:int = 0; var morale:int = 0;
            for(j = 0; j < units.length; ++j)
                if(units[j].key != card.key && GwaiV8Position.has(units[j],35) && (units[j].targets.indexOf(card.template) >= 0 || card.applied.indexOf(units[j].key) >= 0)) ++bonds;
            for(j = 0; j < moraleRoster.length; ++j)
                if(moraleRoster[j].key != card.key && GwaiV8Position.has(moraleRoster[j],32)) ++morale;
            var base:Number = card.power*(GwaiV8Position.isType(card,256) && state.double_spy ? 2 : 1);
            ceiling += (base*(1+bonds)+morale)*(horn ? 2 : 1);
        }
        var destroyed:Object = {}; var weatherRows:Object = {}; var rows:Array = [5,4,3]; var scorchFlags:Array = [7,39,21]; var weatherFlags:Array = [23,24,25];
        for(i = 0; i < hand.length; ++i)
            for(r = 0; r < rows.length; ++r)
            {
                card = hand[i];
                if(GwaiV8Position.has(card,29) || GwaiV8Position.has(card,scorchFlags[r])) destroyed[rows[r]] = true;
                if(GwaiV8Position.isType(card,16) && GwaiV8Position.has(card,weatherFlags[r])) weatherRows[rows[r]] = true;
            }
        var floor:Number = 0;
        for(r = 0; r < rows.length; ++r)
        {
            var row:int = rows[r]; list = state.board[GwaiV8Position.slot(other,row)];
            for(i = 0; i < list.length; ++i)
            {
                card = state.cards[list[i]];
                if(GwaiV8Position.isType(card,128)) { floor += card.power; continue; }
                if(destroyed[row]) continue;
                var value:Number = state.power(card.key);
                if(weatherRows[row])
                    for(j = 0; j < hand.length; ++j)
                        if(GwaiV8Position.isType(hand[j],16) && GwaiV8Position.has(hand[j],weatherFlags[r]))
                        {
                            var projected:Object = state.clone(); projected.addEffect(card.key,hand[j].key);
                            value = Math.min(value,projected.power(card.key)); break;
                        }
                floor += value;
            }
        }
        return [ceiling,floor];
    }
    public static function profile(level:int):Object
    {
        if(level < 0 || level > 3) throw new Error("invalid V8 difficulty");
        return {label:["Easy","Medium","Hard","Expert"][level],search_depth:[1,2,2,3][level],beam_width:[4,8,12,16][level]};
    }
    public static function cachedReserve(state:Object,cache:Object):Number
    {
        var key:String = state.reserveKey();
        if(cache[key] == null) cache[key] = state.reserve();
        return cache[key];
    }
    public static function result(move:Object,path:Array,value:Number,passValue:Number,nodes:int,label:String,unsupported:int,reason:String):Object
    { return {action:move,sequence:path,utility:value,pass_utility:passValue,nodes:nodes,profile:label,unsupported:unsupported,reason:reason,revision:"sequence-v6"}; }
    public static function candidateOrder(a:Object,b:Object):Number
    { return a.value == b.value ? a.order-b.order : b.value-a.value; }
    public static function choose(state:Object,context:Object,level:int = 2):Object
    {
        var config:Object = GwaiV8Sequence.profile(level); var maximum:int = Math.max(32,config.search_depth*config.beam_width*12);
        var mean:Number = GwaiV8Sequence.opponentAverage(state); var cache:Object = {}; var initial:Number = GwaiV8Sequence.cachedReserve(state,cache);
        var passValue:Number = GwaiV8Sequence.utility(state,context,0,initial,mean,true); var scores:Array = state.scores(); var own:int = state.player;
        var tieFinishes:Boolean = context.opponent_losses >= 1 && context.own_losses == 0 && !(context.opponent_faction == 2 && context.own_faction != 2);
        var tieAllowed:Boolean = GwaiV8Sequence.winsTies(context) || tieFinishes;
        var secured:Boolean = context.opponent_passed && (tieAllowed ? scores[own] >= scores[1-own] : scores[own] > scores[1-own]);
        if(secured && (context.opponent_losses >= 1 || context.round_index >= 2))
            return GwaiV8Sequence.result(null,[],1,1,0,config.label,0,"pass_for_match_resources");
        var canPass:Boolean = (context.own_losses == 0 && !context.own_leader_available) || secured;
        for(var i:int = 0; i < state.hand.length; ++i) if(!state.supported(state.cards[state.hand[i]]) && !secured) canPass = false;
        var ceiling:Array = canPass && context.round_index == 1 && context.opponent_losses == 1 ? GwaiV8Sequence.bounds(state) : null;
        if(ceiling != null && (tieAllowed ? ceiling[0] < ceiling[1] : ceiling[0] <= ceiling[1]))
            return GwaiV8Sequence.result(null,[],passValue,passValue,0,config.label,0,"proven_no_supported_overtake");
        var bestValue:Number = canPass ? passValue : -1; var bestPath:Array = []; var beam:Array = [{state:state,path:[]}];
        var nodes:int = 0; var unsupported:int = 0; var rootGains:Object = {};
        for(var depth:int = 0; depth < config.search_depth; ++depth)
        {
            var candidates:Array = [];
            for(i = 0; i < beam.length; ++i)
            {
                var current:Object = beam[i].state; var sequence:Array = beam[i].path;
                if(current.unknown_draws > 0) continue;
                var moves:Array = current.actions();
                for(var j:int = 0; j < moves.length; ++j)
                {
                    if(nodes >= maximum) break;
                    ++nodes; var move:Object = moves[j]; var after:Object;
                    try { after = current.apply(move); }
                    catch(error:Error) { if(!(error is GwaiV8Unsupported)) throw error; ++unsupported; continue; }
                    var path:Array = sequence.concat([move]); var sc:Array = after.scores();
                    if(sequence.length == 0) rootGains[GwaiV8Hash.text(move)] = (sc[own]-sc[1-own])-(scores[own]-scores[1-own]);
                    var kept:Number = GwaiV8Sequence.cachedReserve(after,cache); var value:Number = GwaiV8Sequence.utility(after,context,path.length,kept,mean);
                    if(context.opponent_passed && (tieAllowed ? sc[own] >= sc[1-own] : sc[own] > sc[1-own])) value += 0.00001*kept-0.000001*path.length;
                    var netGain:Number = (sc[own]-sc[1-own])-(scores[own]-scores[1-own]);
                    var beneficial:Boolean = netGain > 0 || kept > initial || after.unknown_draws > 0;
                    if(beneficial && (value > bestValue+1e-12 || (bestPath.length > 0 && Math.abs(value-bestValue) < 1e-12 && rootGains[GwaiV8Hash.text(path[0])] > rootGains[GwaiV8Hash.text(bestPath[0])])) )
                    { bestValue = value; bestPath = path; }
                    candidates.push({value:value,state:after,path:path,order:candidates.length});
                }
                if(nodes >= maximum) break;
            }
            candidates.sort(candidateOrder); beam = candidates.slice(0,config.beam_width);
            if(beam.length == 0 || nodes >= maximum) break;
        }
        return GwaiV8Sequence.result(bestPath.length > 0 ? bestPath[0] : null,bestPath,bestValue,passValue,nodes,config.label,unsupported,
            bestPath.length == 0 && canPass ? "pass_for_match_resources" : bestPath.length > 0 ? "supported_sequence" : "no_supported_plan");
    }
}
