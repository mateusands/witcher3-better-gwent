"""V8 ChoosingMove hooks, appended helpers compile with the full policy classes."""
from v8_runtime_patch import once, add_methods


def patch_ai(source):
    source=source.replace('\r\n','\n')
    if 'function gwaiBeginV8' in source:raise ValueError('AI already patched')
    source=once(source,'import flash.utils.Timer;','import flash.utils.Timer;\n   import flash.utils.getTimer;')
    source=once(source,'protected var _currentRoundCritical:Boolean = false;', '''protected var _currentRoundCritical:Boolean = false;
      private var _gwaiRunner:Object = null;
      private var _gwaiPosition:Object = null;
      private var _gwaiRound:int = -1;
      private var _gwaiLevel:int = -1;
      private var _gwaiReason:String = "";
      private var _gwaiStartedAt:int = 0;
      private var _gwaiFailures:int = 0;
      private var _gwaiStage:String = "";''')
    source=once(source,'protected function state_begin_ChoseMove() : void\n      {',
        'protected function state_begin_ChoseMove() : void\n      {\n         if(this.gwaiBeginV8()) return;')
    source=once(source,'protected function state_update_ChooseMove() : void\n      {',
        'protected function state_update_ChooseMove() : void\n      {\n         if(this.gwaiPumpV8()) return;')
    source=once(source,'protected function state_begin_Idle() : void\n      {',
        'protected function state_begin_Idle() : void\n      {\n         this.gwaiCancelV8();')
    # These are used only by the native fallback when enabled. Off stays vanilla.
    old='gameFlowControllerRef.playerControllers[opponentID].currentRoundStatus'
    safe='(gameFlowControllerRef.gwaiProfileForPlayer(playerID) >= 0 ? gameFlowControllerRef.playerControllers[opponentID].gwaiObservedRoundStatus : gameFlowControllerRef.playerControllers[opponentID].currentRoundStatus)'
    if source.count(old)!=2:raise ValueError('opponent status anchor count')
    source=source.replace(old,safe)
    for side in ['playerID','opponentID']:
        old='cardManagerRef.playerDeckDefinitions['+side+'].getDeckFaction()'
        safe='(gameFlowControllerRef.gwaiProfileForPlayer(playerID) >= 0 ? cardManagerRef.getCardLeader('+side+').templateRef.factionIdx : '+old+')'
        source=once(source,old,safe)
    return add_methods(source,'''      public function gwaiCancelV8() : void
      {
         if(this._gwaiRunner != null) this._gwaiRunner.cancel();
         this._gwaiRunner = null; this._gwaiPosition = null;
         this._gwaiRound = -1; this._gwaiLevel = -1;
         CardManager.getInstance().gwaiClearPlan(this.playerID);
      }
      public function gwaiShutdownV8() : void
      {
         this.gwaiCancelV8();
         if(this.waitingTimer != null)
         {
            this.waitingTimer.stop();
            this.waitingTimer.removeEventListener(TimerEvent.TIMER_COMPLETE,this.onWaitingTimerEnded);
            this.waitingTimer = null;
         }
         this.waitingForTimer = false; this._decidedCardTransaction = null;
         this.transactionCard = null; this.attitude = TACTIC_NONE; this._turnOver = true;
         this._stateMachine.ChangeState("Idle");
      }
      // Diagnostics: always logged; the recorder build also writes an "X" event.
      public function gwaiNote(text:String) : void
      {
         text = text.split(";").join(",").split(String.fromCharCode(34)).join("'").split(String.fromCharCode(10)).join(" ");
         CardManager.log("#GWAI# " + text);
         /*GWAI_REC_NOTE*/
      }
      public function gwaiBeginV8() : Boolean
      {
         this.gwaiCancelV8(); this._gwaiReason = "";
         var level:int = this.gameFlowControllerRef.gwaiProfileForPlayer(this.playerID);
         if(level < 0) return false;
         // A V8 failure must never stall the match: any error hands the turn to the native AI.
         try
         {
            var manager:CardManager = CardManager.getInstance();
            this._gwaiPosition = GwaiV8Capture.capture(manager,this.playerID);
            var context:Object = GwaiV8Context.capture(manager,this.gameFlowControllerRef,this._gwaiPosition);
            this._gwaiRound = this.gameFlowControllerRef.gwaiRoundIndex; this._gwaiLevel = level;
            this._gwaiRunner = new GwaiV8Runner(this._gwaiPosition,context,level);
         }
         catch(error:Error)
         {
            this._gwaiFailures++;
            this.gwaiNote("v8_error:begin:" + error.message);
            this._gwaiRunner = null; this._gwaiPosition = null;
            CardManager.getInstance().gwaiClearPlan(this.playerID);
            return false;
         }
         this._gwaiStartedAt = getTimer();
         this._decidedCardTransaction = null; this.attitude = TACTIC_NONE;
         return true;
      }
      // Opening exchange (Medium and above), proven in the Lab: up to two own cards go back to
      // the deck, chosen from the own remaining composition only (never the shuffled order).
      // A weather card the leader can pull from the deck goes back first.
      // Same steps as CardManager.mulliganCard, without its hero-drawn sound, which would tell
      // the player what the NPC drew.
      public function gwaiNpcMulligan() : void
      {
         var level:int = this.gameFlowControllerRef.gwaiProfileForPlayer(this.playerID);
         if(level < 1) return;
         try
         {
            var manager:CardManager = CardManager.getInstance();
            var deck:GwintDeck = manager.playerDeckDefinitions[this.playerID];
            var started:int = getTimer();
            for(var turn:int = 0; turn < 2; ++turn)
            {
               var state:GwaiV8Position = GwaiV8Capture.capture(manager,this.playerID);
               var leader:CardLeaderInstance = manager.getCardLeader(this.playerID);
               var key:int = GwaiV8Mulligan.chooseWithLeader(state,leader == null ? -1 : leader.templateRef.getFirstEffect());
               if(key < 0) break;
               var card:CardInstance = manager.getCardInstance(key);
               if(card == null || manager.getCardInstanceList(CardManager.CARD_LIST_LOC_HAND,this.playerID).indexOf(card) < 0)
                  throw new Error("exchange source outside own hand");
               deck.readdCard(card.templateId);
               var drawn:int = deck.drawCard();
               if(drawn == CardInstance.INVALID_INSTANCE_ID) throw new Error("exchange draw failed");
               var fresh:CardInstance = manager.spawnCardInstance(drawn,this.playerID);
               manager.addCardInstanceToList(fresh,CardManager.CARD_LIST_LOC_HAND,this.playerID);
               manager.returnCardToDeck(card);
               this.gwaiNote("npc_mulligan:" + card.templateId + ">" + drawn);
            }
            this.gwaiNote("npc_mulligan_done:" + turn + ":" + (getTimer() - started) + "ms:lvl=" + level);
         }
         catch(error:Error)
         {
            this._gwaiFailures++;
            this.gwaiNote("v8_error:mulligan:" + error.message);
         }
      }
      public function gwaiAllowedPass(reason:String) : Boolean
      { return ["pass_for_match_resources","proven_no_supported_overtake","concede_unwinnable_chase"].indexOf(reason) >= 0; }
      public function gwaiNativeFallback(reason:String) : void
      {
         var manager:CardManager = CardManager.getInstance(); manager.gwaiClearPlan(this.playerID);
         // Recalculate ONLY own hand; native helpers may use own/public graves.
         var hand:Vector.<CardInstance> = manager.getCardInstanceList(CardManager.CARD_LIST_LOC_HAND,this.playerID);
         for(var i:int = 0; i < hand.length; ++i) hand[i].recalculatePowerPotential(manager);
         this.ChooseAttitude(); this._decidedCardTransaction = this.decideWhichCardToPlay();
         if(this._decidedCardTransaction == null) this.attitude = TACTIC_PASS;
         this._gwaiReason = "native_fallback:"+reason;
         CardManager.log("#GWAI# " + this._gwaiReason);
      }
      public function gwaiPumpV8() : Boolean
      {
         if(this._gwaiRunner == null) return false;
         var flow:GwintGameFlowController = this.gameFlowControllerRef;
         if(flow.playerControllers[this.playerID] != this)
         {
            this.gwaiCancelV8(); this._decidedCardTransaction = null; this.attitude = TACTIC_NONE;
            this._stateMachine.ChangeState("Idle"); return true;
         }
         if(!flow.gameStarted || flow.currentPlayer != this.playerID || flow.gwaiRoundIndex != this._gwaiRound ||
            flow.gwaiProfileForPlayer(this.playerID) != this._gwaiLevel)
         {
            // Still this controller's ChooseMove: decide natively instead of idling (an idle
            // controller that never ends its turn stalls the match).
            this.gwaiNote("v8_stale:started=" + flow.gameStarted + ",current=" + flow.currentPlayer +
               ",round=" + flow.gwaiRoundIndex + "/" + this._gwaiRound);
            this.gwaiCancelV8(); this.gwaiNativeFallback("stale_search"); return false;
         }
         try
         {
            if(getTimer() - this._gwaiStartedAt > this.gwaiTimeLimit())
            {
               // Use the best evaluated root move if any; only an empty search hands over natively.
               if(!this._gwaiRunner.done && this._gwaiRunner.roots != null && this._gwaiRunner.roots.length > 0)
               {
                  this.gwaiNote("v8_timeout_partial:" + (getTimer() - this._gwaiStartedAt) + "ms:roots=" + this._gwaiRunner.roots.length);
                  this._gwaiRunner.exhausted = true; this._gwaiRunner.finish();
                  return this.gwaiPumpV8Step(flow);
               }
               this.gwaiNote("v8_timeout:" + (getTimer() - this._gwaiStartedAt) + "ms");
               this.gwaiCancelV8(); this.gwaiNativeFallback("timeout"); return false;
            }
            return this.gwaiPumpV8Step(flow);
         }
         catch(error:Error)
         {
            this._gwaiFailures++;
            var phase:String = this._gwaiRunner != null ? String(this._gwaiRunner.phase) : "none";
            this.gwaiNote("v8_error:pump:" + this._gwaiStage + ":phase=" + phase + ":" + error.toString());
            this.gwaiCancelV8(); this.gwaiNativeFallback("error");
         }
         return false;
      }
      // Per-difficulty thinking limit (ms): Easy, Normal, Hard (Expert: no longer offered). When reached, the best
      // evaluated root move is played (v8_timeout_partial); only an empty search hands over.
      private function gwaiTimeLimit() : int
      {
         return [2000,4000,6000,8000][Math.max(0,Math.min(3,this._gwaiLevel))];
      }
      // Recorded with every decision so in-game speed can be measured per difficulty.
      private function gwaiDecisionStats() : String
      {
         var nodes:int = this._gwaiRunner != null && this._gwaiRunner.engine != null ? int(this._gwaiRunner.engine.nodes) : -1;
         return (getTimer() - this._gwaiStartedAt) + "ms:nodes=" + nodes + ":lvl=" + this._gwaiLevel;
      }
      private function gwaiPumpV8Step(flow:GwintGameFlowController) : Boolean
      {
         this._gwaiStage = "advance";
         if(!this._gwaiRunner.advance(1024,20,getTimer)) return true;
         this._gwaiStage = "result";
         var result:Object = this._gwaiRunner.output;
         if(result == null) throw new Error("V8 runner completed without result");
         if(result.action == null && !this.gwaiAllowedPass(result.reason))
         {
            if(result.reason != "no_supported_plan" && result.reason != "insufficient_public_catalog")
               throw new Error("unknown V8 pass reason: "+result.reason);
            this.gwaiNativeFallback(result.reason);
            this.gwaiNote("v8_native:" + result.reason + ":" + this.gwaiDecisionStats());
         }
         else
         {
            this._gwaiStage = "prepare";
            var prepared:Object = GwaiV8Execution.prepare(CardManager.getInstance(),flow,this._gwaiPosition,result);
            this._decidedCardTransaction = prepared.transaction;
            this.attitude = prepared.passing ? TACTIC_PASS : TACTIC_AVERAGE_WIN;
            this._gwaiReason = prepared.reason;
            this.gwaiNote("v8:" + this._gwaiReason + ":" + this.gwaiDecisionStats());
         }
         // Keep prepared effect choices alive until ApplyingCard/Idle completes.
         this._gwaiRunner = null; this._gwaiPosition = null;
         return false;
      }
''')
