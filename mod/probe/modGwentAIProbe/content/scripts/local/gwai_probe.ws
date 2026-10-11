// Gwent AI probe.
// Stage 1 (done): SetRawConfigValueByStr + SaveUserSettings writes to dx12user.settings.
// Stage 2: the probe code in content/blob0.bundle (gwint_game.redswf) runs when a Gwent
// match starts and sends its results here; they are stored in section [GwaiProbe2] as
// r0000, r0001, ... = "<name>|=|<data>", and "count" = "<sent>/<stored>".

@addField( CR4GwintGameMenu ) var gwaiProbeIdx : int;

function GwaiPad4( v : int ) : string
{
	if ( v < 10 ) { return "000" + IntToString( v ); }
	if ( v < 100 ) { return "00" + IntToString( v ); }
	if ( v < 1000 ) { return "0" + IntToString( v ); }
	return IntToString( v );
}

@addMethod( CR4GwintGameMenu ) event OnGwaiProbe( probeName : string, probeData : string )
{
	theGame.GetInGameConfigWrapper().SetRawConfigValueByStr( "GwaiProbe2", "r" + GwaiPad4( gwaiProbeIdx ), probeName + "|=|" + probeData );
	gwaiProbeIdx += 1;
}

@addMethod( CR4GwintGameMenu ) event OnGwaiProbeEnd( sent : int )
{
	theGame.GetInGameConfigWrapper().SetRawConfigValueByStr( "GwaiProbe2", "count", IntToString( sent ) + "/" + IntToString( gwaiProbeIdx ) );
	theGame.SaveUserSettings();
	theGame.GetGuiManager().ShowNotification( "Gwent AI probe: " + IntToString( gwaiProbeIdx ) + " results saved" );
}
