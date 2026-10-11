// SHA-256 for the ASCII-only canonical public numeric position/context payload.
// This is deterministic seeding, never an input from a hidden opponent deck.
internal class GwaiV8Hash
{
    public static var K:Array = [0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,
        0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,
        0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,
        0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,
        0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,
        0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,
        0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,
        0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2];
    public static function rotate(v:uint,n:int):uint
    { return uint((v >>> n) | (v << (32-n))); }
    public static function digest(text:String):Array
    {
        var bytes:Array = [];
        for(var i:int = 0; i < text.length; ++i)
        {
            var code:int = text.charCodeAt(i);
            if(code > 127) throw new Error("non-ASCII public seed payload");
            bytes.push(code);
        }
        var bits:Number = bytes.length*8; bytes.push(128);
        while(bytes.length%64 != 56) bytes.push(0);
        var high:uint = uint(Math.floor(bits/4294967296.0)); var low:uint = uint(bits);
        for(i = 3; i >= 0; --i) bytes.push((high >>> (i*8)) & 255);
        for(i = 3; i >= 0; --i) bytes.push((low >>> (i*8)) & 255);
        var hash:Array = [0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19];
        for(var offset:int = 0; offset < bytes.length; offset += 64)
        {
            var words:Array = [];
            for(i = 0; i < 16; ++i)
                words.push(uint((bytes[offset+i*4] << 24) | (bytes[offset+i*4+1] << 16) | (bytes[offset+i*4+2] << 8) | bytes[offset+i*4+3]));
            for(i = 16; i < 64; ++i)
            {
                var s0:uint = uint(GwaiV8Hash.rotate(words[i-15],7) ^ GwaiV8Hash.rotate(words[i-15],18) ^ (uint(words[i-15]) >>> 3));
                var s1:uint = uint(GwaiV8Hash.rotate(words[i-2],17) ^ GwaiV8Hash.rotate(words[i-2],19) ^ (uint(words[i-2]) >>> 10));
                words.push(uint(Number(words[i-16])+s0+Number(words[i-7])+s1));
            }
            var a:uint = uint(hash[0]); var b:uint = uint(hash[1]); var c:uint = uint(hash[2]); var d:uint = uint(hash[3]);
            var e:uint = uint(hash[4]); var f:uint = uint(hash[5]); var g:uint = uint(hash[6]); var h:uint = uint(hash[7]);
            for(i = 0; i < 64; ++i)
            {
                s1 = uint(GwaiV8Hash.rotate(e,6) ^ GwaiV8Hash.rotate(e,11) ^ GwaiV8Hash.rotate(e,25));
                var choose:uint = uint((e & f) ^ (~e & g));
                var t1:uint = uint(Number(h)+s1+choose+Number(K[i])+Number(words[i]));
                s0 = uint(GwaiV8Hash.rotate(a,2) ^ GwaiV8Hash.rotate(a,13) ^ GwaiV8Hash.rotate(a,22));
                var majority:uint = uint((a & b) ^ (a & c) ^ (b & c)); var t2:uint = uint(Number(s0)+majority);
                h = g; g = f; f = e; e = uint(Number(d)+t1); d = c; c = b; b = a; a = uint(Number(t1)+t2);
            }
            var updated:Array = [a,b,c,d,e,f,g,h];
            for(i = 0; i < 8; ++i) hash[i] = uint(Number(hash[i])+Number(updated[i]));
        }
        return hash;
    }
    // JSON.stringify equivalent (compact, insertion key order). The game's Scaleform
    // runtime has no JSON class (Error #1065 in game), so V8 must not use it.
    public static function text(value:Object):String
    {
        if(value === null || value === undefined) return "null";
        if(value is Boolean) return value ? "true" : "false";
        if(value is Number) return isFinite(value) ? String(value) : "null";
        if(value is String)
        {
            var out:String = "\"";
            for(var c:int = 0; c < value.length; ++c)
            {
                var code:int = value.charCodeAt(c);
                if(code == 34) out += "\\\"";
                else if(code == 92) out += "\\\\";
                else if(code == 10) out += "\\n";
                else if(code == 13) out += "\\r";
                else if(code == 9) out += "\\t";
                else if(code < 32) out += "\\u" + ("0000" + code.toString(16)).substr(-4);
                else out += value.charAt(c);
            }
            return out + "\"";
        }
        var parts:Array = [];
        var j:int;
        if(value is Array)
        {
            for(j = 0; j < value.length; ++j) parts.push(GwaiV8Hash.text(value[j]));
            return "[" + parts.join(",") + "]";
        }
        for(var key:String in value) parts.push(GwaiV8Hash.text(key) + ":" + GwaiV8Hash.text(value[key]));
        return "{" + parts.join(",") + "}";
    }
    public static function canonical(value:Object):String
    {
        if(value == null) return "null";
        if(value is Array)
        {
            var parts:Array = [];
            for(var i:int = 0; i < value.length; ++i) parts.push(GwaiV8Hash.canonical(value[i]));
            return "["+parts.join(", ")+"]";
        }
        if(value is Boolean || value is Number || value is String) return GwaiV8Hash.text(value);
        var keys:Array = []; for(var key:String in value) keys.push(key); keys.sort(); parts = [];
        for(i = 0; i < keys.length; ++i) parts.push(GwaiV8Hash.text(keys[i])+": "+GwaiV8Hash.canonical(value[keys[i]]));
        return "{"+parts.join(", ")+"}";
    }
}
