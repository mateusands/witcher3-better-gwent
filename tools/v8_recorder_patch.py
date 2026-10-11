"""Additional combined-recorder lifecycle; keep passive logs separate from policy."""
from pathlib import Path
from build_recorder import once


def patch_restart(files):
    block=(Path(__file__).parent/'recorder_as/CardManager.restart.txt').read_text()
    files['CardManager']=once(files['CardManager'],'      public function CardManager()',block+'      public function CardManager()')
    files['GwintGameFlowController']=once(files['GwintGameFlowController'],
        'this.cardManager.reset();','this.cardManager.reset();\n         this.cardManager.gwaiRecorderRestart();')
    # Flush a direct close or confirmed surrender; final matches are idempotent.
    files['GwintGameMenu']=once(files['GwintGameMenu'],
        'public function gwaiStopMatch(request:Boolean) : void\n      {',
        'public function gwaiStopMatch(request:Boolean) : void\n      {\n         CardManager.gwaiEnd("close");')
    files['GwintGameMenu']=once(files['GwintGameMenu'],
        'protected function onGameFlowDone(hasWon:Boolean) : void\n      {',
        'protected function onGameFlowDone(hasWon:Boolean) : void\n      {\n         CardManager.gwaiEnd("close");')
