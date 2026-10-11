// Resumable own-action stage: one projected action evaluation per step.
internal class GwaiV8SequenceTask
{
    public var position:Object = null;
    public var context:Object = null;
    public var config:Object = null;
    public var cache:Object = {};
    public var maximum:int = 0;
    public var mean:Number = 0;
    public var initial:Number = 0;
    public var passValue:Number = 0;
    public var scores:Array = [];
    public var own:int = 0;
    public var tieAllowed:Boolean = false;
    public var canPass:Boolean = false;
    public var bestValue:Number = 0;
    public var bestPath:Array = [];
    public var beam:Array = [];
    public var candidates:Array = [];
    public var rootGains:Object = {};
    public var depth:int = 0;
    public var beamIndex:int = 0;
    public var moveIndex:int = 0;
    public var moves:Array = null;
    public var nodes:int = 0;
    public var unsupported:int = 0;
    public var output:Object = null;
    public function GwaiV8SequenceTask(state:Object,ctx:Object,level:int)
    {
        position = state; context = ctx; config = GwaiV8Sequence.profile(level);
        maximum = Math.max(32,config.search_depth*config.beam_width*12);
        mean = GwaiV8Sequence.opponentAverage(state); initial = GwaiV8Sequence.cachedReserve(state,cache);
        passValue = GwaiV8Sequence.utility(state,ctx,0,initial,mean,true); scores = state.scores(); own = state.player;
        tieAllowed = GwaiV8Sequence.winsTies(ctx) || GwaiV8Response.tieMatch(ctx);
        var secure:Boolean = ctx.opponent_passed && (tieAllowed ? scores[own] >= scores[1-own] : scores[own] > scores[1-own]);
        if(secure && (ctx.opponent_losses >= 1 || ctx.round_index >= 2))
        { output = GwaiV8Sequence.result(null,[],1,1,0,config.label,0,"pass_for_match_resources"); return; }
        canPass = (ctx.own_losses == 0 && !ctx.own_leader_available) || secure;
        for(var i:int = 0; i < state.hand.length; ++i) if(!state.supported(state.cards[state.hand[i]]) && !secure) canPass = false;
        var bounds:Array = canPass && ctx.round_index == 1 && ctx.opponent_losses == 1 ? GwaiV8Sequence.bounds(state) : null;
        if(bounds != null && (tieAllowed ? bounds[0] < bounds[1] : bounds[0] <= bounds[1]))
        { output = GwaiV8Sequence.result(null,[],passValue,passValue,0,config.label,0,"proven_no_supported_overtake"); return; }
        bestValue = canPass ? passValue : -1; beam = [{state:state,path:[]}];
    }
    public function finish():void
    {
        output = GwaiV8Sequence.result(bestPath.length > 0 ? bestPath[0] : null,bestPath,bestValue,passValue,nodes,config.label,unsupported,
            bestPath.length == 0 && canPass ? "pass_for_match_resources" : bestPath.length > 0 ? "supported_sequence" : "no_supported_plan");
    }
    public function step():void
    {
        if(output != null) return;
        while(true)
        {
            if(nodes >= maximum || depth >= config.search_depth || beam.length == 0) { finish(); return; }
            if(beamIndex >= beam.length)
            {
                candidates.sort(GwaiV8Sequence.candidateOrder); beam = candidates.slice(0,config.beam_width);
                candidates = []; beamIndex = 0; moves = null; ++depth; continue;
            }
            var entry:Object = beam[beamIndex]; var current:Object = entry.state; var sequence:Array = entry.path;
            if(current.unknown_draws > 0) { ++beamIndex; moves = null; continue; }
            if(moves == null) { moves = current.actions(); moveIndex = 0; }
            if(moveIndex >= moves.length) { ++beamIndex; moves = null; continue; }
            var move:Object = moves[moveIndex]; ++moveIndex; ++nodes; var after:Object;
            try { after = current.apply(move); }
            catch(error:Error) { if(!(error is GwaiV8Unsupported)) throw error; ++unsupported; return; }
            var path:Array = sequence.concat([move]); var sc:Array = after.scores();
            if(sequence.length == 0) rootGains[GwaiV8Hash.text(move)] = (sc[own]-sc[1-own])-(scores[own]-scores[1-own]);
            var kept:Number = GwaiV8Sequence.cachedReserve(after,cache); var value:Number = GwaiV8Sequence.utility(after,context,path.length,kept,mean);
            if(context.opponent_passed && (tieAllowed ? sc[own] >= sc[1-own] : sc[own] > sc[1-own])) value += 0.00001*kept-0.000001*path.length;
            var netGain:Number = (sc[own]-sc[1-own])-(scores[own]-scores[1-own]);
            var beneficial:Boolean = netGain > 0 || kept > initial || after.unknown_draws > 0;
            if(beneficial && (value > bestValue+1e-12 || (bestPath.length > 0 && Math.abs(value-bestValue) < 1e-12 && rootGains[GwaiV8Hash.text(path[0])] > rootGains[GwaiV8Hash.text(bestPath[0])])) )
            { bestValue = value; bestPath = path; }
            candidates.push({value:value,state:after,path:path,order:candidates.length}); return;
        }
    }
}
