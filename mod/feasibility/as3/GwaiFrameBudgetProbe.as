// Original dummy workload probe. No card, deck, rule or game RNG access.
internal class GwaiFrameBudgetProbe
{
    private static var active:Boolean = false;
    private static var host:flash.display.DisplayObject;
    private static var started:int;
    private static var frames:uint = 0;
    private static var iterations:uint = 0;
    private static var maxBatchMs:int = 0;
    private static var checksum:uint = 17;

    public static function attach(menu:flash.display.DisplayObject) : void
    {
        if(active || menu == null) return;
        active = true;
        host = menu;
        started = flash.utils.getTimer();
        frames = 0;
        iterations = 0;
        maxBatchMs = 0;
        checksum = 17;
        host.addEventListener(flash.events.Event.ENTER_FRAME, onFrame, false, 0, true);
        host.addEventListener(flash.events.Event.REMOVED_FROM_STAGE, onRemoved, false, 0, true);
    }

    private static function detach() : void
    {
        if(host != null)
        {
            host.removeEventListener(flash.events.Event.ENTER_FRAME, onFrame);
            host.removeEventListener(flash.events.Event.REMOVED_FROM_STAGE, onRemoved);
        }
        host = null;
        active = false;
    }

    private static function onRemoved(event:flash.events.Event) : void
    {
        // Closing the menu cancels the incomplete measurement and releases the
        // host. A later match may attach a fresh probe without stale listeners.
        detach();
    }

    private static function onFrame(event:flash.events.Event) : void
    {
        var batchStart:int = flash.utils.getTimer();
        var count:uint = 0;
        // Fixed operation cap plus a cooperative millisecond deadline. Timer
        // granularity can overshoot one chunk; this is not a hard real-time bound.
        while(count < 512)
        {
            checksum = uint(checksum * 1664525 + 1013904223);
            ++count;
            if((count & 15) == 0 && flash.utils.getTimer() - batchStart >= 2) break;
        }
        iterations += count;
        ++frames;
        var spent:int = flash.utils.getTimer() - batchStart;
        if(spent > maxBatchMs) maxBatchMs = spent;
        var elapsed:int = flash.utils.getTimer() - started;
        if(elapsed >= 10000)
        {
            var target:flash.display.DisplayObject = host;
            var metrics:Array = [int(iterations), elapsed, int(frames), maxBatchMs, int(checksum),
                int(iterations * 1000.0 / elapsed)];
            detach();
            target.dispatchEvent(new red.core.events.GameEvent(red.core.events.GameEvent.CALL,
                "OnGwaiSearchProbe", metrics));
        }
    }
}
