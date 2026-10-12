// Fair runtime context: public engine-observed status, counts/results and leaders.
// Never invokes the opponent's native currentRoundStatus/canBeUsed getters.
internal class GwaiV8Context
{
    // Cards publicly known to be in the opponent's hand (back from the board, e.g. by Decoy).
    // Off until a Lab A/B proves the gain; the list then stays empty, exactly as before.
    public static const USE_KNOWN_HAND:Boolean = false;
    public static function capture(manager:Object,flow:Object,state:Object):Object
    {
        var own:int = state.player; var other:int = 1-own; var losses:Array = [0,0];
        for(var i:int = 0; i < manager.roundResults.length; ++i)
        {
            var result:Object = manager.roundResults[i];
            if(!result.played) continue;
            var winner:int = result.getRoundWinner();
            if(winner != 0) ++losses[0]; if(winner != 1) ++losses[1];
        }
        var ownLeader:Object = state.cards[state.leaders[own]]; var enemyLeader:Object = state.cards[state.leaders[other]];
        if(ownLeader == null || enemyLeader == null) throw new Error("public leaders not spawned");
        return {round_index:flow.gwaiRoundIndex,own_losses:losses[own],opponent_losses:losses[other],
            opponent_passed:flow.playerControllers[other].gwaiObservedRoundStatus == 2,
            opponent_hand_count:manager.gwaiPublicHandCount(other),own_faction:ownLeader.faction,opponent_faction:enemyLeader.faction,
            // Same meaning as the Python controller: only a leader the model cannot search blocks
            // passing / keeps the generic credit. Using leader_ready here forbade every pass while
            // a modeled leader was unused (in-game round-one overcommit, in-game match g126).
            own_leader_available:state.leaderUnmodeled(own),opponent_leader_available:state.leaderUnmodeled(other),
            opponent_known:GwaiV8Context.USE_KNOWN_HAND ? manager.gwaiKnownHand(other) : []};
    }
}
