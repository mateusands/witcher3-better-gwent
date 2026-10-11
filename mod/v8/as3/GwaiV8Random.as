// Isolated deterministic MT19937 integer seeding and 53-bit draws matching Python.
// Never calls Math.random or consumes the game's random stream.
internal class GwaiV8Random
{
    public var mt:Array = [];
    public var index:int = 624;
    public static function multiply(a:uint,b:uint):uint
    { return uint((a & 65535)*(b & 65535)+(((a >>> 16)*(b & 65535)+(a & 65535)*(b >>> 16)) << 16)); }
    public function GwaiV8Random(words:Array)
    {
        var seed:Array = words.slice();
        while(seed.length > 1 && seed[seed.length-1] == 0) seed.pop();
        if(seed.length == 0) seed.push(0);
        mt.push(uint(19650218));
        for(var n:int = 1; n < 624; ++n) mt.push(uint(GwaiV8Random.multiply(1812433253,uint(mt[n-1]) ^ (uint(mt[n-1]) >>> 30))+n));
        var i:int = 1; var j:int = 0;
        for(n = 0; n < Math.max(624,seed.length); ++n)
        {
            mt[i] = uint((uint(mt[i]) ^ GwaiV8Random.multiply(uint(mt[i-1]) ^ (uint(mt[i-1]) >>> 30),1664525))+Number(seed[j])+j);
            ++i; ++j;
            if(i >= 624) { mt[0] = mt[623]; i = 1; }
            if(j >= seed.length) j = 0;
        }
        for(n = 0; n < 623; ++n)
        {
            mt[i] = uint((uint(mt[i]) ^ GwaiV8Random.multiply(uint(mt[i-1]) ^ (uint(mt[i-1]) >>> 30),1566083941))-i);
            ++i; if(i >= 624) { mt[0] = mt[623]; i = 1; }
        }
        mt[0] = uint(0x80000000);
    }
    public function nextWord():uint
    {
        if(index >= 624)
        {
            for(var i:int = 0; i < 624; ++i)
            {
                var y:uint = uint((uint(mt[i]) & 0x80000000) | (uint(mt[(i+1)%624]) & 0x7fffffff));
                mt[i] = uint(uint(mt[(i+397)%624]) ^ (y >>> 1) ^ ((y & 1) != 0 ? 0x9908b0df : 0));
            }
            index = 0;
        }
        y = uint(mt[index]); ++index;
        y = uint(y ^ (y >>> 11)); y = uint(y ^ ((y << 7) & 0x9d2c5680));
        y = uint(y ^ ((y << 15) & 0xefc60000)); return uint(y ^ (y >>> 18));
    }
    public function random():Number
    {
        var a:uint = nextWord() >>> 5; var b:uint = nextWord() >>> 6;
        return (a*67108864.0+b)/9007199254740992.0;
    }
}
