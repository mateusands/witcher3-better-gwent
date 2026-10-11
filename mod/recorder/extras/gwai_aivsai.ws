// Optional add-on for the recorder: forces every Gwent match to AI vs AI (the player's side is
// played by the game's AI). Copy next to gwai_recorder.ws only for unattended recording.

@wrapMethod( CR4GwintManager ) function getDoubleAIEnabled() : bool
{
	wrappedMethod();
	return true;
}

