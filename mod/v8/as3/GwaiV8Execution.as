// Validated real transaction/choice plan. No hypothetical cards enter native state.
internal class GwaiV8Execution
{
    public static function prepare(manager:Object,flow:Object,state:Object,result:Object):Object
    {
        var side:int = state.player; manager.gwaiClearPlan(side);
        if(flow.currentPlayer != side || flow.gwaiRoundIndex < 0) throw new Error("stale V8 turn");
        if(result.action == null) return {transaction:null,passing:true,reason:result.reason};
        var move:Object = result.action;
        if(state.hand.indexOf(move.source) < 0 && move.source != state.leaders[side]) throw new Error("source outside own hand/leader");
        // Check full projected action/chain before retaining any native references.
        state.apply(move);
        var source:Object = manager.getCardInstance(move.source);
        if(source == null || source.instanceId != move.source || (source.inList != 1 && source.inList != 10) || source.listsPlayer != side)
            throw new Error("stale V8 source");
        var transaction:Object = new CardTransaction(); transaction.sourceCardInstanceRef = source;
        transaction.targetSlotID = move.slot; transaction.targetPlayerID = side;
        var card:Object = state.cards[move.source];
        if(GwaiV8Position.isType(card,256)) transaction.targetPlayerID = 1-side;
        if(GwaiV8Position.isType(card,16)) transaction.targetPlayerID = -1;
        if(GwaiV8Position.has(card,26))
        {
            var target:Object = manager.getCardInstance(move.target);
            if(target == null || target.instanceId != move.target || target.listsPlayer != side || [5,4,3].indexOf(target.inList) < 0)
                throw new Error("stale V8 Decoy target");
            transaction.targetCardInstanceRef = target;
        }
        var chain:Array = [];
        for(var i:int = 0; i < move.chain.length; ++i) chain.push(move.chain[i].slice());
        manager.gwaiStorePlan(side,{side:side,round:flow.gwaiRoundIndex,source:move.source,target:move.target,
            expectedMedic:move.source,chain:chain,placements:{},reason:result.reason});
        return {transaction:transaction,passing:false,reason:result.reason};
    }
}
