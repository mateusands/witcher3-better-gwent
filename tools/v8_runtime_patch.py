"""Original native public-context/settings bridge patches, not a decision hook."""
NATIVE_CLASSES = ['BasePlayerController','GwintGameFlowController','CardManager','GwintGameMenu','CardInstance','CardLeaderInstance']


def once(source, old, new):
    if source.count(old) != 1:
        raise ValueError('native patch anchor count: '+repr(old[:80]))
    return source.replace(old,new,1)


def add_methods(source, methods):
    last=source.rfind('}')
    end=source.rfind('}',0,last)
    return source[:end]+methods+'\n'+source[end:]


def patch(name, source):
    if 'function gwai' in source or 'function get gwai' in source or 'gwaiNurseChoice(' in source or 'gwaiLeaderTarget(' in source:
        raise ValueError('native bridge already patched')
    source=source.replace('\r\n','\n')
    if name=='BasePlayerController':
        source=once(source,'public function resetCurrentRoundStatus() : void\n      {',
            'public function resetCurrentRoundStatus() : void\n      {\n         if(this.gameFlowControllerRef != null && this.gameFlowControllerRef.gwaiProfileForPlayer(this.playerID) >= 0)\n         {\n            var manager:CardManager = CardManager.getInstance();\n            var leader:CardLeaderInstance = manager.getCardLeader(this.playerID);\n            this.currentRoundStatus = manager.gwaiPublicHandCount(this.playerID) > 0 || (leader != null && leader.canBeUsed) ? ROUND_PLAYER_STATUS_ACTIVE : ROUND_PLAYER_STATUS_DONE;\n            return;\n         }')
        source=once(source,'private var _currentRoundStatus:int = 1;',
            'private var _currentRoundStatus:int = 1;\n      private var _gwaiObservedRoundStatus:int = 1;')
        source=once(source,'return ROUND_PLAYER_STATUS_DONE;',
            'this._gwaiObservedRoundStatus = ROUND_PLAYER_STATUS_DONE;\n            return ROUND_PLAYER_STATUS_DONE;')
        source=once(source,'return this._currentRoundStatus;',
            'this._gwaiObservedRoundStatus = this._currentRoundStatus;\n         return this._currentRoundStatus;')
        source=once(source,'this._currentRoundStatus = value;',
            'this._currentRoundStatus = value;\n         this._gwaiObservedRoundStatus = value;')
        source=once(source,'this.gameFlowControllerRef.playerControllers[this.opponentID].currentRoundStatus == ROUND_PLAYER_STATUS_DONE',
            '(this.gameFlowControllerRef.gwaiProfileForPlayer(this.playerID) >= 0 ? this.gameFlowControllerRef.playerControllers[this.opponentID].gwaiObservedRoundStatus : this.gameFlowControllerRef.playerControllers[this.opponentID].currentRoundStatus) == ROUND_PLAYER_STATUS_DONE')
        return add_methods(source,'''      // Read only an explicit pass or status already observed by native flow.
      public function get gwaiObservedRoundStatus() : int
      { return this._gwaiObservedRoundStatus; }
''')
    if name=='CardManager':
        source=once(source,'protected static var _instance:CardManager;','protected static var _instance:CardManager;\n      private var _gwaiPlans:Object = {0:null,1:null};\n      private var _gwaiKnown:Object = {};')
        # A card that goes back to a hand from a public list (graveyard, rows, weather) is known
        # to everyone; same rule as sim/gwentsim/known_hand.py.
        source=once(source,'var oldListID:* = cardInstance.inList;',
            'var oldListID:* = cardInstance.inList;\n         if(newListID == CARD_LIST_LOC_HAND && oldListID >= CARD_LIST_LOC_GRAVEYARD && oldListID <= CARD_LIST_LOC_WEATHERSLOT) this._gwaiKnown[cardInstance.instanceId] = true;\n         else delete this._gwaiKnown[cardInstance.instanceId];')
        return add_methods(source,'''      public function gwaiKnownHand(side:int) : Array
      {
         var out:Array = []; var hand:Vector.<CardInstance> = this.getCardInstanceList(CARD_LIST_LOC_HAND,side);
         for(var i:int = 0; i < hand.length; ++i) if(this._gwaiKnown[hand[i].instanceId]) out.push(hand[i].templateId);
         out.sort(Array.NUMERIC); return out;
      }
      public function gwaiPublicHandCount(side:int) : int
      { return this.getCardInstanceList(CARD_LIST_LOC_HAND,side).length; }
      public function gwaiClearPlan(side:int) : void
      { this._gwaiPlans[side] = null; }
      public function gwaiStorePlan(side:int,plan:Object) : void
      { this._gwaiPlans[side] = plan; }
      public function gwaiActivePlan(side:int) : Object
      {
         var plan:Object = this._gwaiPlans[side]; var flow:GwintGameFlowController = GwintGameFlowController.getInstance();
         if(plan == null) return null;
         if(flow == null || flow.currentPlayer != side || flow.gwaiRoundIndex != plan.round)
         { this.gwaiClearPlan(side); return null; }
         return plan;
      }
      public function gwaiLeaderTarget(side:int,source:int) : int
      { var plan:Object = this.gwaiActivePlan(side); return plan != null && plan.source == source ? int(plan.target) : -1; }
      public function gwaiNurseChoice(side:int,source:int,eligible:Object) : int
      {
         var plan:Object = this.gwaiActivePlan(side);
         if(plan == null || plan.expectedMedic != source || plan.chain.length == 0) return -1;
         var step:Array = plan.chain[0]; var target:CardInstance = null;
         for(var i:int = 0; i < eligible.length; ++i) if(eligible[i].instanceId == step[0]) target = eligible[i];
         var flag:int = step[1] == 5 ? 1 : step[1] == 4 ? 2 : step[1] == 3 ? 4 : -1;
         if(target == null || !target.templateRef.isType(flag) || target.templateRef.isType(CardTemplate.CardType_Hero))
         { this.gwaiClearPlan(side); return -1; }
         plan.chain.shift(); plan.expectedMedic = target.instanceId;
         plan.placements[target.instanceId] = {row:step[1],side:target.templateRef.isType(CardTemplate.CardType_Spy) ? 1-side : side};
         return target.instanceId;
      }
      public function gwaiTakePlacement(side:int,instance:int) : Object
      {
         var plan:Object = this.gwaiActivePlan(side);
         if(plan == null) return null;
         var placement:Object = plan.placements[instance]; delete plan.placements[instance]; return placement;
      }
''')
    if name=='GwintGameFlowController':
        source=once(source,'protected function state_update_Initializing() : void\n      {',
            'protected function state_update_Initializing() : void\n      {\n         if(!this.gwaiSettingsReady) return;')
        source=once(source,'if(this.playerControllers[CardManager.PLAYER_1] is HumanPlayerController)\n         {\n            (this.playerControllers[CardManager.PLAYER_1] as HumanPlayerController).setChoiceDialog(this.mcChoiceDialog);',
            'this.gwaiApplyControllers();\n         if(this.playerControllers[CardManager.PLAYER_1] is HumanPlayerController)\n         {\n            (this.playerControllers[CardManager.PLAYER_1] as HumanPlayerController).setChoiceDialog(this.mcChoiceDialog);')
        # NPC opening exchange right after the deal, while the player's own exchange dialog opens.
        source=once(source,'this.cardManager.shuffleAndDrawCards();',
            'this.cardManager.shuffleAndDrawCards();\n         if(this.playerControllers[CardManager.PLAYER_2] is AIPlayerController) (this.playerControllers[CardManager.PLAYER_2] as AIPlayerController).gwaiNpcMulligan();')
        source=once(source,'protected function state_begin_reset() : void\n      {',
            'protected function state_begin_reset() : void\n      {\n         this.gwaiStopSearches();')
        source=once(source,'protected function state_begin_ShowingFinalResult() : void\n      {',
            'protected function state_begin_ShowingFinalResult() : void\n      {\n         this.gwaiStopSearches();')
        source=once(source,'public var gameStarted:Boolean = false;',
            'public var gameStarted:Boolean = false;\n      private var _gwaiMatchSettings:Object = null;')
        return add_methods(source,'''      public function get gwaiRoundIndex() : int
      { return this.currentRound; }
      public function gwaiConfigure(data:Object) : Boolean
      {
         // First valid packet captures this menu's match intent; later edits wait.
         if(this._gwaiMatchSettings != null || this.gameStarted || data == null || data.version !== 1) return false;
         var level:int = 2;
         if(data.difficulty === 0 || data.difficulty === 1 || data.difficulty === 2) level = int(data.difficulty);   // Expert (3) is Hard
         var enabled:Boolean = data.enabled === true;
         this._gwaiMatchSettings = {enabled:enabled,difficulty:level,autoplay:enabled && data.autoplay === true};
         return true;
      }
      public function gwaiApplyControllers() : void
      {
         if(this._gwaiMatchSettings == null || !this._gwaiMatchSettings.enabled) return;
         // Apply once before native initialization binds renderers and buttons.
         var old:Object = this.playerControllers[0];
         var wantAI:Boolean = this._gwaiMatchSettings.autoplay;
         if((wantAI && old is AIPlayerController) || (!wantAI && old is HumanPlayerController)) return;
         if(old is AIPlayerController) old.gwaiShutdownV8();
         var replacement:BasePlayerController = wantAI ? new AIPlayerController() : new HumanPlayerController();
         replacement.gameFlowControllerRef = this; replacement.playerID = 0; replacement.opponentID = 1;
         this.playerControllers[0] = replacement;
      }
      public function gwaiStopSearches() : void
      {
         this.gameStarted = false;
         for(var side:int = 0; side < this.playerControllers.length; ++side)
         {
            var controller:Object = this.playerControllers[side];
            if(controller is AIPlayerController) controller.gwaiShutdownV8();
            CardManager.getInstance().gwaiClearPlan(side);
         }
      }
      public function get gwaiSettingsReady() : Boolean
      { return this._gwaiMatchSettings != null; }
      public function gwaiProfileForPlayer(side:int) : int
      {
         if(side != 0 && side != 1) return -1;
         if(this._gwaiMatchSettings == null || !this._gwaiMatchSettings.enabled) return -1;
         if(side == 0 && !this._gwaiMatchSettings.autoplay) return -1;
         return int(this._gwaiMatchSettings.difficulty);
      }
      public function gwaiSettingsSnapshot() : Object
      {
         if(this._gwaiMatchSettings == null) return null;
         return {enabled:this._gwaiMatchSettings.enabled,difficulty:this._gwaiMatchSettings.difficulty,autoplay:this._gwaiMatchSettings.autoplay};
      }
''')
    if name=='GwintGameMenu':
        source=once(source,'public function setAIEnabled(turnAIOn:Boolean) : void\n      {',
            'public function setAIEnabled(turnAIOn:Boolean) : void\n      {\n         var gwaiSettings:Object = this.gameFlowController.gwaiSettingsSnapshot();\n         if(gwaiSettings != null && gwaiSettings.enabled) return;')
        source=once(source,'protected function onGameFlowDone(hasWon:Boolean) : void\n      {',
            'protected function onGameFlowDone(hasWon:Boolean) : void\n      {\n         this.gameFlowController.gwaiStopSearches();')
        source=once(source,'dispatchEvent(new GameEvent(GameEvent.REGISTER,"gwint.game.toggleAI",[this.setAIEnabled]));',
            'dispatchEvent(new GameEvent(GameEvent.REGISTER,"gwint.game.toggleAI",[this.setAIEnabled]));\n         dispatchEvent(new GameEvent(GameEvent.REGISTER,"gwai.match.settings",[this.gwaiConfigureMatch]));\n         dispatchEvent(new GameEvent(GameEvent.REGISTER,"gwai.match.stop",[this.gwaiStopMatch]));')
        return add_methods(source,'''      public function gwaiConfigureMatch(data:Object) : void
      { this.gameFlowController.gwaiConfigure(data); }
      public function gwaiStopMatch(request:Boolean) : void
      { this.gameFlowController.gwaiStopSearches(); }
''')
    if name=='CardInstance':
        source=once(source,'this.log("Applying Nurse Effect");','this.log("Applying Nurse Effect");\n            var gwaiChoice:int = cardManagerRef.gwaiNurseChoice(this.listsPlayer,this.instanceId,copyList);')
        source=once(source,'this.handleNurseChoice(copyList[Math.min(Math.floor(Math.random() * copyList.length),copyList.length - 1)].instanceId);','cardManagerRef.gwaiClearPlan(this.listsPlayer);\n                  this.handleNurseChoice(copyList[Math.min(Math.floor(Math.random() * copyList.length),copyList.length - 1)].instanceId);')
        source=once(source,'else if(gameFlowRef.playerControllers[this.listsPlayer] is AIPlayerController)','else if(gwaiChoice >= 0)\n               {\n                  this.handleNurseChoice(gwaiChoice);\n               }\n               else if(gameFlowRef.playerControllers[this.listsPlayer] is AIPlayerController)')
        source=once(source,'cardInstance.recalculatePowerPotential(cardManagerRef);\n            cardManagerRef.addCardInstanceToList(cardInstance,cardInstance.getOptimalTransaction().targetSlotID,cardInstance.getOptimalTransaction().targetPlayerID);',
            'var gwaiPlacement:Object = cardManagerRef.gwaiTakePlacement(this.listsPlayer,cardInstance.instanceId);\n            if(gwaiPlacement != null)\n            {\n               cardManagerRef.addCardInstanceToList(cardInstance,int(gwaiPlacement.row),int(gwaiPlacement.side));\n            }\n            else\n            {\n               cardInstance.recalculatePowerPotential(cardManagerRef);\n               cardManagerRef.addCardInstanceToList(cardInstance,cardInstance.getOptimalTransaction().targetSlotID,cardInstance.getOptimalTransaction().targetPlayerID);\n            }')
        return source
    if name=='CardLeaderInstance':
        for effect in ('CardEffect_Resurect_Enemy','CardEffect_Resurect'):
            anchor='case CardTemplate.'+effect+':\n               if(isAI && !cardManagerRef.cardEffectManager.randomResEnabled)'
            replacement='case CardTemplate.'+effect+':\n               if(isAI && cardManagerRef.gwaiLeaderTarget(owningPlayer,instanceId) >= 0 && !cardManagerRef.cardEffectManager.randomResEnabled)\n               {\n                  this.handleResurrectChoice(cardManagerRef.gwaiLeaderTarget(owningPlayer,instanceId));\n               }\n               else if(isAI && !cardManagerRef.cardEffectManager.randomResEnabled)'
            source=once(source,anchor,replacement)
        source=once(source,'protected function pickWeather(isAI:Boolean) : void\n      {\n         var cardManagerRef:CardManager = CardManager.getInstance();',
            'protected function pickWeather(isAI:Boolean) : void\n      {\n         var cardManagerRef:CardManager = CardManager.getInstance();\n         if(isAI && cardManagerRef.gwaiLeaderTarget(owningPlayer,instanceId) >= 0)\n         {\n            this.handleCardDrawChoice_Weather(cardManagerRef.gwaiLeaderTarget(owningPlayer,instanceId));\n            return;\n         }')
        return source
    raise ValueError('unrecognized native class: '+name)
