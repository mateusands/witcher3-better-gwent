// Full alternating public-belief response-search stage; hypotheses never execute.
internal class GwaiV8Response
{
    public var position:Object = null;
    public var context:Object = null;
    public var level:int = 0;
    public var config:Object = null;
    public var mean:Number = 0;
    public var cache:Object = {};
    public var nodes:int = 0;
    public var unsupported:int = 0;
    public var budget:int = 0;
    public static function tieMatch(ctx:Object):Boolean
    { return ctx.opponent_losses >= 1 && ctx.own_losses == 0 && !(ctx.opponent_faction == 2 && ctx.own_faction != 2); }
    public static function secured(state:Object,ctx:Object):Boolean
    {
        var scores:Array = state.scores(); var gap:Number = scores[state.player]-scores[1-state.player];
        return GwaiV8Sequence.winsTies(ctx) || GwaiV8Response.tieMatch(ctx) ? gap >= 0 : gap > 0;
    }
    public static function same(a:Object,b:Object):Boolean
    { return GwaiV8Hash.canonical(a) == GwaiV8Hash.canonical(b); }
    public static function inert(before:Object,after:Object,move:Object):Boolean
    {
        if(move.source == before.leaders[before.player])
            return GwaiV8Response.same(before.board,after.board) && GwaiV8Response.same(before.grave,after.grave) && GwaiV8Response.same(before.hand,after.hand) && GwaiV8Response.same(before.counts,after.counts);
        var card:Object = before.cards[move.source];
        return (GwaiV8Position.has(card,29) || GwaiV8Position.isType(card,16)) && GwaiV8Response.same(before.board,after.board);
    }
    public static function result(move:Object,value:Number,passValue:Number,samples:int,nodes:int,unsupported:int,unresolved:Boolean,reason:String,alternatives:Array = null,exhausted:Boolean = false):Object
    { return {action:move,value:value,pass_value:passValue,samples:samples,nodes:nodes,unsupported:unsupported,unresolved_leader:unresolved,reason:reason,alternatives:alternatives == null ? [] : alternatives,budget_exhausted:exhausted,revision:"response-v7"}; }
    public function charge():void
    { if(nodes >= budget) throw new GwaiV8Budget("V8 search budget reached"); ++nodes; }
    public function reserve(state:Object):Number
    { return GwaiV8Sequence.cachedReserve(state,cache); }
    public static function hypothesisState(view:Object):Object
    {
        var hand:Array = []; var counts:Array = []; var unresolved:int = 0;
        for(var i:int = 0; i < view.hand.length; ++i)
        { var card:Object = view.cards[view.hand[i]]; hand.push(card); if(!view.supported(card)) ++unresolved; }
        for(var key:String in view.counts) counts.push([int(key),view.counts[key]]);
        counts.sort(GwaiV8Position.firstKeyOrder);
        return {hand:hand,counts:counts,unsupported:unresolved,prior:"continuation"};
    }
    public function outcome(state:Object,after:Object,passing:Boolean,enemyPassed:Boolean = false):Object
    {
        var own:Object = after.clone(); own.player = position.player; own.hand = state.hand;
        own.counts = GwaiV8Position.copyMap(state.counts); own.unknown_draws = state.unknown_draws; own.draw_value = state.draw_value;
        var ctx:Object = GwaiV8Position.copyMap(context); ctx.opponent_hand_count = after.hand.length+after.unknown_draws;
        ctx.opponent_passed = enemyPassed; ctx.opponent_leader_available = after.leaderUnmodeled(after.player);
        return {value:GwaiV8Sequence.utility(own,ctx,1,reserve(own),mean,passing,reserve(after)),
            publicState:own,hypothesis:GwaiV8Response.hypothesisState(after),enemy_passed:enemyPassed};
    }
    public function response(state:Object,hypothesis:Object,passing:Boolean = false):Object
    {
        var view:Object = GwaiV8Belief.opponentView(state,hypothesis);
        var flipped:Object = GwaiV8Position.copyMap(context);
        flipped.own_losses = context.opponent_losses; flipped.opponent_losses = context.own_losses;
        flipped.own_faction = context.opponent_faction; flipped.opponent_faction = context.own_faction;
        var choices:Array = [];
        if(flipped.own_losses == 0 || (passing && GwaiV8Response.secured(view,flipped))) choices.push(outcome(state,view,passing,true));
        var moves:Array = view.actions();
        for(var i:int = 0; i < moves.length; ++i)
        {
            charge(); var after:Object;
            try { after = view.apply(moves[i]); }
            catch(error:Error) { if(!(error is GwaiV8Unsupported)) throw error; ++unsupported; continue; }
            choices.push(outcome(state,after,passing));
        }
        if(choices.length == 0) choices.push(outcome(state,view,passing,true));
        var best:Object = choices[0];
        for(i = 1; i < choices.length; ++i) if(choices[i].value < best.value) best = choices[i];
        return best;
    }
    public static function rootOrder(a:Object,b:Object):Number
    { return a.value == b.value ? a.order-b.order : b.value-a.value; }
    public static function choose(state:Object,ctx:Object,difficulty:int = 2):Object
    {
        var engine:Object = new GwaiV8Response(); engine.position = state; engine.context = ctx; engine.level = difficulty;
        engine.config = GwaiV8Sequence.profile(difficulty); return engine.search();
    }
    public function search():Object
    {
        if(context.opponent_passed)
        {
            var exact:Object = GwaiV8Sequence.choose(position,context,level);
            return GwaiV8Response.result(exact.action,exact.utility,exact.pass_utility,0,exact.nodes,exact.unsupported,false,exact.reason);
        }
        var samples:int = level == 0 ? 2 : level == 3 ? 6 : 4;
        var beliefs:Array = GwaiV8Belief.hypotheses(position,context,samples);
        if(beliefs.length == 0) return GwaiV8Response.result(null,0,0,0,0,0,context.opponent_leader_available,"insufficient_public_catalog");
        mean = GwaiV8Sequence.opponentAverage(position); budget = [512,2048,4096,8192][level];
        for(var i:int = 0; i < beliefs.length; ++i) unsupported += beliefs[i].unsupported;
        var passSum:Number = 0;
        try { for(i = 0; i < beliefs.length; ++i) passSum += response(position,beliefs[i],true).value; }
        catch(error:Error)
        {
            if(!(error is GwaiV8Budget)) throw error;
            return GwaiV8Response.result(null,0,0,beliefs.length,nodes,unsupported,context.opponent_leader_available,"no_supported_plan",null,true);
        }
        var passValue:Number = passSum/beliefs.length;
        var canPass:Boolean = context.own_losses == 0 && !context.own_leader_available;
        for(i = 0; i < position.hand.length; ++i) if(!position.supported(position.cards[position.hand[i]])) canPass = false;
        var bestValue:Number = canPass ? passValue : -1; var best:Object = null; var roots:Array = []; var exhausted:Boolean = false;
        var moves:Array = position.actions();
        for(i = 0; i < moves.length; ++i)
        {
            try { charge(); }
            catch(error:Error) { if(!(error is GwaiV8Budget)) throw error; exhausted = true; break; }
            var move:Object = moves[i]; var state:Object;
            try { state = position.apply(move); }
            catch(error:Error) { if(!(error is GwaiV8Unsupported)) throw error; ++unsupported; continue; }
            if(GwaiV8Response.inert(position,state,move)) continue;
            var outcomes:Array = []; var total:Number = 0;
            try
            {
                for(var j:int = 0; j < beliefs.length; ++j)
                { var entry:Object = response(state,beliefs[j]); outcomes.push(entry); total += entry.value; }
            }
            catch(error:Error) { if(!(error is GwaiV8Budget)) throw error; exhausted = true; break; }
            var value:Number = total/outcomes.length;
            roots.push({value:value,action:move,state:state,outcomes:outcomes,order:roots.length});
            if(value > bestValue+1e-12) { bestValue = value; best = move; }
        }
        roots.sort(rootOrder);
        if(config.search_depth >= 2 && !exhausted)
            for(i = 0; i < Math.min(roots.length,config.beam_width); ++i)
            {
                var root:Object = roots[i]; var values:Array = [];
                for(j = 0; j < root.outcomes.length; ++j)
                {
                    entry = root.outcomes[j]; var publicState:Object = entry.publicState; var h:Object = entry.hypothesis;
                    if(publicState.unknown_draws > 0 || publicState.hand.length == 0) { values.push(entry.value); continue; }
                    if(entry.enemy_passed)
                    {
                        var passed:Object = GwaiV8Position.copyMap(context); passed.opponent_passed = true; passed.opponent_hand_count = h.hand.length;
                        exact = GwaiV8Sequence.choose(publicState,passed,level); values.push(exact.utility); continue;
                    }
                    var future:Number = entry.value; var continuations:Array = publicState.actions();
                    for(var k:int = 0; k < continuations.length; ++k)
                    {
                        try { charge(); }
                        catch(error:Error) { if(!(error is GwaiV8Budget)) throw error; exhausted = true; break; }
                        var after:Object;
                        try { after = publicState.apply(continuations[k]); }
                        catch(error:Error) { if(!(error is GwaiV8Unsupported)) throw error; ++unsupported; continue; }
                        if(GwaiV8Response.inert(publicState,after,continuations[k])) continue;
                        try { future = Math.max(future,response(after,h).value); }
                        catch(error:Error) { if(!(error is GwaiV8Budget)) throw error; exhausted = true; break; }
                    }
                    if(exhausted) break; values.push(future);
                }
                if(exhausted) break;
                total = 0; for(j = 0; j < values.length; ++j) total += values[j]; value = total/values.length;
                if(value > bestValue+1e-12) { bestValue = value; best = root.action; }
            }
        var alternatives:Array = [];
        for(i = 0; i < roots.length; ++i) alternatives.push({action:roots[i].action,oneTurnValue:roots[i].value});
        return GwaiV8Response.result(best,bestValue,passValue,beliefs.length,nodes,unsupported,context.opponent_leader_available,
            best != null ? "supported_response" : canPass ? "pass_for_match_resources" : "no_supported_plan",alternatives,exhausted);
    }
}
internal class GwaiV8Budget extends Error
{
    public function GwaiV8Budget(message:String) { super(message); }
}
