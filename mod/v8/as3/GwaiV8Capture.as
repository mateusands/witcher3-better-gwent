// Fair information boundary. Catalog is public; only own remaining composition
// is copied. The opponent leader getter can inspect its deck, so use hasBeenUsed.
internal class GwaiV8Capture
{
    public static function templateCard(t:CardTemplate, player:int):Object
    {
        return {key:0,template:t.index,power:t.power,types:t.typeArray,
            effects:t.effectFlags.slice(),targets:t.summonFlags == null ? [] : t.summonFlags.slice(),
            owner:player,player:player,row:1,applied:[],faction:t.factionIdx,banished_on_clear:false};
    }
    public static function observe(state:GwaiV8Position, unit:CardInstance):void
    {
        if(state.cards[unit.instanceId] != null) return;
        var card:Object = GwaiV8Capture.templateCard(unit.templateRef,state.player);
        card.key = unit.instanceId; card.owner = unit.owningPlayer;
        card.player = unit.listsPlayer; card.row = unit.inList; card.applied = [];
        card.banished_on_clear = unit.BanishInsteadOfGraveyard;
        state.cards[card.key] = card;
        for(var i:int = 0; i < unit.effectedByCardsRefList.length; ++i)
        {
            var effect:CardInstance = unit.effectedByCardsRefList[i];
            card.applied.push(effect.instanceId); GwaiV8Capture.observe(state,effect);
        }
    }
    public static function capture(manager:CardManager, own:int):GwaiV8Position
    {
        var state:GwaiV8Position = new GwaiV8Position(); state.player = own;
        var list:Vector.<CardInstance> = manager.getCardInstanceList(1,own);
        for(var i:int = 0; i < list.length; ++i)
        { GwaiV8Capture.observe(state,list[i]); state.hand.push(list[i].instanceId); }
        var rows:Array = [5,4,3,6,7,8];
        for(var side:int = 0; side < 2; ++side)
        {
            state.grave[side] = [];
            list = manager.getCardInstanceList(2,side);
            for(i = 0; i < list.length; ++i) { GwaiV8Capture.observe(state,list[i]); state.grave[side].push(list[i].instanceId); }
            for(var r:int = 0; r < rows.length; ++r)
            {
                var loc:String = GwaiV8Position.slot(side,rows[r]); state.board[loc] = [];
                list = manager.getCardInstanceList(rows[r],side);
                for(i = 0; i < list.length; ++i) { GwaiV8Capture.observe(state,list[i]); state.board[loc].push(list[i].instanceId); }
            }
            for(r = 0; r < 3; ++r)
            {
                loc = GwaiV8Position.slot(side,rows[r]); state.effects[loc] = [];
                list = manager.cardEffectManager.getEffectsForList(rows[r],side);
                for(i = 0; i < list.length; ++i) { GwaiV8Capture.observe(state,list[i]); state.effects[loc].push(list[i].instanceId); }
            }
            var leader:CardLeaderInstance = manager.getCardLeader(side);
            state.leaders[side] = leader == null ? null : leader.instanceId;
            if(leader != null) GwaiV8Capture.observe(state,leader);
            state.leader_ready[side] = leader != null && (side == own ? leader.canBeUsed : !leader.hasBeenUsed);
            state.half_weather[side] = manager.halfWeatherEnabled(side);
        }
        state.board[GwaiV8Position.slot(-1,9)] = [];
        list = manager.getCardInstanceList(9,-1);
        for(i = 0; i < list.length; ++i) { GwaiV8Capture.observe(state,list[i]); state.board[GwaiV8Position.slot(-1,9)].push(list[i].instanceId); }
        // This is the ONLY remaining-deck lookup. No shuffled order survives.
        var indices:Vector.<int> = manager.playerDeckDefinitions[own].cardIndicesInDeck;
        for(i = 0; i < indices.length; ++i)
        {
            var index:int = indices[i];
            state.counts[index] = state.counts[index] == null ? 1 : int(state.counts[index])+1;
        }
        for(var key:Object in manager._cardTemplates)
            state.catalog[key] = GwaiV8Capture.templateCard(manager._cardTemplates[key],own);
        state.double_spy = manager.cardEffectManager.doubleSpyEnabled;
        state.random_recovery = manager.cardEffectManager.randomResEnabled;
        var values:Object = manager.cardValues.getEffectValueDictionary();
        for(key in values) state.weights[key] = values[key];
        state.weights.weather = manager.cardValues.weatherCardValue;
        return state;
    }
}
