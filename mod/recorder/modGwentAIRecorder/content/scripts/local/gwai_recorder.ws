// Gwent AI recorder (test mod, not for release).
// - Matches are played normally by the player; the player's actions are recorded too, so the
//   simulator can replay them. For unattended AI vs AI matches, add extras/gwai_aivsai.ws.
// - content/blob0.bundle (gwint_game.redswf with recording hooks) sends the match record in
//   chunks; they are stored in dx12user.settings, section [GwaiRec]:
//     games      = number of matches started
//     gNNN_SSSS  = chunk SSSS of match NNN
//     gNNN_end   = "<chunks sent>/<chunks stored>/<reason>"   (reason: final or quit)

@addField( CR4GwintGameMenu ) var gwaiGame : int;
@addField( CR4GwintGameMenu ) var gwaiGameSet : bool;
@addField( CR4GwintGameMenu ) var gwaiRecv : int;

function GwaiRecPad( v : int, digits : int ) : string
{
	var s : string = IntToString( v );
	while ( StrLen( s ) < digits )
	{
		s = "0" + s;
	}
	return s;
}

@addMethod( CR4GwintGameMenu ) function GwaiRecGameKey() : string
{
	var cfg : CInGameConfigWrapper = theGame.GetInGameConfigWrapper();

	if ( !gwaiGameSet )
	{
		// Numbering starts at 100 so new recordings never reuse the names of g000-g008.
		gwaiGame = StringToInt( cfg.GetRawConfigValueByStr( "GwaiRec", "games" ), 100 );
		if ( gwaiGame < 100 )
		{
			gwaiGame = 100;
		}
		cfg.SetRawConfigValueByStr( "GwaiRec", "games", IntToString( gwaiGame + 1 ) );
		gwaiGameSet = true;
	}
	return "g" + GwaiRecPad( gwaiGame, 3 );
}

// Internal rematch starts a new record; cancelled surrender keeps the same one.
@addMethod( CR4GwintGameMenu ) event OnGwaiStart()
{
    gwaiGameSet = false;
    gwaiRecv = 0;
}

@addMethod( CR4GwintGameMenu ) event OnGwaiRec( seq : int, chunk : string )
{
	theGame.GetInGameConfigWrapper().SetRawConfigValueByStr( "GwaiRec", GwaiRecGameKey() + "_" + GwaiRecPad( seq, 4 ), chunk );
	gwaiRecv += 1;
}

@addMethod( CR4GwintGameMenu ) event OnGwaiEnd( chunks : int, reason : string )
{
	theGame.GetInGameConfigWrapper().SetRawConfigValueByStr( "GwaiRec", GwaiRecGameKey() + "_end", IntToString( chunks ) + "/" + IntToString( gwaiRecv ) + "/" + reason );
	theGame.SaveUserSettings();
	theGame.GetGuiManager().ShowNotification( "Gwent AI recorder: match " + IntToString( gwaiGame ) + " saved (" + IntToString( gwaiRecv ) + " chunks, " + reason + ")" );
}
