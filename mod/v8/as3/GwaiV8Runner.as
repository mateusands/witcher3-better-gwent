// Cooperative response/sequence runner; yields between complete action evaluations.
// Clock deadlines are checked between steps, not a hard bound on one evaluation.
internal class GwaiV8Runner
{
    public var position:Object = null;
    public var context:Object = null;
    public var level:int = 2;
    public var engine:Object = null;
    public var phase:String = "initialize";
    public var done:Boolean = false;
    public var cancelled:Boolean = false;
    public var output:Object = null;
    public var sequenceTask:Object = null;
    public var reply:Object = null;
    public var beliefs:Array = [];
    public var beliefIndex:int = 0;
    public var passSum:Number = 0;
    public var passValue:Number = 0;
    public var canPass:Boolean = false;
    public var bestValue:Number = 0;
    public var best:Object = null;
    public var roots:Array = [];
    public var rootMoves:Array = [];
    public var rootMoveIndex:int = 0;
    public var rootState:Object = null;
    public var rootMove:Object = null;
    public var outcomes:Array = [];
    public var rootIndex:int = 0;
    public var outcomeIndex:int = 0;
    public var values:Array = [];
    public var publicState:Object = null;
    public var hypothesis:Object = null;
    public var continuations:Array = [];
    public var continuationIndex:int = 0;
    public var future:Number = 0;
    public var exhausted:Boolean = false;
    public var lastSteps:int = 0;
    public function GwaiV8Runner(state:Object,ctx:Object,difficulty:int = 2)
    {
        position = state; context = ctx; level = difficulty;
        engine = new GwaiV8Response(); engine.position = state; engine.context = ctx; engine.level = level;
        engine.config = GwaiV8Sequence.profile(level);
    }
    public function cancel():void
    { cancelled = true; done = true; output = null; reply = null; sequenceTask = null; }
    public function finishRaw(raw:Object):void
    { output = GwaiV8Policy.guards(position,context,raw); done = true; reply = null; sequenceTask = null; }
    public function finish():void
    {
        roots.sort(GwaiV8Response.rootOrder); var alternatives:Array = [];
        for(var i:int = 0; i < roots.length; ++i) alternatives.push({action:roots[i].action,oneTurnValue:roots[i].value});
        finishRaw(GwaiV8Response.result(best,bestValue,passValue,beliefs.length,engine.nodes,engine.unsupported,context.opponent_leader_available,
            best != null ? "supported_response" : canPass ? "pass_for_match_resources" : "no_supported_plan",alternatives,exhausted));
    }
    public function beginReply(state:Object,h:Object,passing:Boolean = false):void
    {
        var view:Object = GwaiV8Belief.opponentView(state,h); var flipped:Object = GwaiV8Position.copyMap(context);
        flipped.own_losses = context.opponent_losses; flipped.opponent_losses = context.own_losses;
        flipped.own_faction = context.opponent_faction; flipped.opponent_faction = context.own_faction;
        var first:Object = null;
        if(flipped.own_losses == 0 || (passing && GwaiV8Response.secured(view,flipped))) first = engine.outcome(state,view,passing,true);
        reply = {state:state,view:view,passing:passing,moves:view.actions(),index:0,best:first,done:false};
    }
    public function stepReply():void
    {
        if(reply.index >= reply.moves.length)
        {
            if(reply.best == null) reply.best = engine.outcome(reply.state,reply.view,reply.passing,true);
            reply.done = true; return;
        }
        engine.charge(); var move:Object = reply.moves[reply.index]; ++reply.index; var after:Object;
        try { after = reply.view.apply(move); }
        catch(error:Error) { if(!(error is GwaiV8Unsupported)) throw error; ++engine.unsupported; return; }
        var choice:Object = engine.outcome(reply.state,after,reply.passing);
        if(reply.best == null || choice.value < reply.best.value) reply.best = choice;
    }
    public function tick():void
    {
        var i:int; var total:Number; var value:Number; var after:Object;
        if(phase == "initialize")
        {
            if(context.opponent_passed)
            { sequenceTask = new GwaiV8SequenceTask(position,context,level); phase = "exactInitial"; return; }
            beliefs = GwaiV8Belief.hypotheses(position,context,level == 0 ? 2 : level == 3 ? 6 : 4);
            if(beliefs.length == 0)
            { finishRaw(GwaiV8Response.result(null,0,0,0,0,0,context.opponent_leader_available,"insufficient_public_catalog")); return; }
            engine.mean = GwaiV8Sequence.opponentAverage(position); engine.budget = [512,768,2048,8192][level];
            for(i = 0; i < beliefs.length; ++i) engine.unsupported += beliefs[i].unsupported;
            phase = "passes"; return;
        }
        if(phase == "exactInitial" || phase == "exactContinuation")
        {
            sequenceTask.step(); if(sequenceTask.output == null) return;
            var exact:Object = sequenceTask.output;
            if(phase == "exactInitial")
            { finishRaw(GwaiV8Response.result(exact.action,exact.utility,exact.pass_utility,0,exact.nodes,exact.unsupported,false,exact.reason)); return; }
            values.push(exact.utility); ++outcomeIndex; sequenceTask = null; phase = "continueEntry"; return;
        }
        if(phase == "passes")
        {
            if(reply == null) { beginReply(position,beliefs[beliefIndex],true); return; }
            stepReply(); if(!reply.done) return;
            passSum += reply.best.value; reply = null; ++beliefIndex;
            if(beliefIndex < beliefs.length) return;
            passValue = passSum/beliefs.length; canPass = context.own_losses == 0 && !context.own_leader_available;
            for(i = 0; i < position.hand.length; ++i) if(!position.supported(position.cards[position.hand[i]])) canPass = false;
            bestValue = canPass ? passValue : -1; rootMoves = position.actions(); phase = "root"; return;
        }
        if(phase == "root")
        {
            if(rootMoveIndex >= rootMoves.length)
            {
                roots.sort(GwaiV8Response.rootOrder);
                if(engine.config.search_depth < 2) { finish(); return; }
                phase = "continueEntry"; return;
            }
            engine.charge(); rootMove = rootMoves[rootMoveIndex]; ++rootMoveIndex;
            try { rootState = position.apply(rootMove); }
            catch(error:Error) { if(!(error is GwaiV8Unsupported)) throw error; ++engine.unsupported; return; }
            if(GwaiV8Response.inert(position,rootState,rootMove)) return;
            outcomes = []; beliefIndex = 0; phase = "rootReplies"; return;
        }
        if(phase == "rootReplies")
        {
            if(reply == null) { beginReply(rootState,beliefs[beliefIndex]); return; }
            stepReply(); if(!reply.done) return;
            outcomes.push(reply.best); reply = null; ++beliefIndex;
            if(beliefIndex < beliefs.length) return;
            total = 0; for(i = 0; i < outcomes.length; ++i) total += outcomes[i].value; value = total/outcomes.length;
            roots.push({value:value,action:rootMove,state:rootState,outcomes:outcomes,order:roots.length});
            if(value > bestValue+1e-12) { bestValue = value; best = rootMove; }
            phase = "root"; return;
        }
        if(phase == "continueEntry")
        {
            if(rootIndex >= Math.min(roots.length,engine.config.beam_width)) { finish(); return; }
            var root:Object = roots[rootIndex];
            if(outcomeIndex >= root.outcomes.length)
            {
                total = 0; for(i = 0; i < values.length; ++i) total += values[i]; value = total/values.length;
                if(value > bestValue+1e-12) { bestValue = value; best = root.action; }
                values = []; outcomeIndex = 0; ++rootIndex; return;
            }
            var entry:Object = root.outcomes[outcomeIndex]; publicState = entry.publicState; hypothesis = entry.hypothesis;
            if(publicState.unknown_draws > 0 || publicState.hand.length == 0) { values.push(entry.value); ++outcomeIndex; return; }
            if(entry.enemy_passed)
            {
                var passed:Object = GwaiV8Position.copyMap(context); passed.opponent_passed = true; passed.opponent_hand_count = hypothesis.hand.length;
                sequenceTask = new GwaiV8SequenceTask(publicState,passed,level); phase = "exactContinuation"; return;
            }
            future = entry.value; continuations = publicState.actions(); continuationIndex = 0; phase = "continueOwn"; return;
        }
        if(phase == "continueOwn")
        {
            if(continuationIndex >= continuations.length) { values.push(future); ++outcomeIndex; phase = "continueEntry"; return; }
            engine.charge(); var move:Object = continuations[continuationIndex]; ++continuationIndex;
            try { after = publicState.apply(move); }
            catch(error:Error) { if(!(error is GwaiV8Unsupported)) throw error; ++engine.unsupported; return; }
            if(GwaiV8Response.inert(publicState,after,move)) return;
            beginReply(after,hypothesis); phase = "continueReply"; return;
        }
        if(phase == "continueReply")
        {
            stepReply(); if(!reply.done) return;
            future = Math.max(future,reply.best.value); reply = null; phase = "continueOwn"; return;
        }
        throw new Error("invalid V8 runner phase");
    }
    public function advance(maxSteps:int = 32,maxMillis:int = 2,clock:Function = null):Boolean
    {
        if(maxSteps < 1 || maxMillis < 1) throw new Error("invalid V8 slice budget");
        lastSteps = 0; var start:Number = clock == null ? 0 : clock();
        while(!done && lastSteps < maxSteps)
        {
            if(lastSteps > 0 && clock != null && clock()-start >= maxMillis) break;
            ++lastSteps;
            try { tick(); }
            catch(error:Error)
            {
                if(!(error is GwaiV8Budget)) throw error;
                exhausted = true;
                if(phase == "passes") finishRaw(GwaiV8Response.result(null,0,0,beliefs.length,engine.nodes,engine.unsupported,context.opponent_leader_available,"no_supported_plan",null,true));
                else finish();
            }
        }
        return done;
    }
}
