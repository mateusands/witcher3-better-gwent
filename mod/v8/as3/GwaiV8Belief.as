// Explicit public-catalog sensitivity hypotheses, not the actual player's range.
internal class GwaiV8Belief
{
    public static function boardOrder(a:Array,b:Array):Number
    { return a[0][0] == b[0][0] ? a[0][1]-b[0][1] : a[0][0]-b[0][0]; }
    public static function publicPayload(state:Object,context:Object):Array
    {
        var cards:Array = []; var counts:Array = []; var board:Array = []; var key:String;
        for(key in state.cards)
        {
            var card:Object = state.cards[key]; cards.push([int(key),card.template,card.owner,card.player,card.row,card.applied]);
        }
        cards.sort(GwaiV8Position.firstKeyOrder);
        for(key in state.counts) counts.push([int(key),state.counts[key]]);
        counts.sort(GwaiV8Position.firstKeyOrder);
        for(key in state.board)
        {
            var pair:Array = key.split(":"); board.push([[int(pair[0]),int(pair[1])],state.board[key]]);
        }
        board.sort(boardOrder); return [state.player,context,state.hand,cards,counts,board];
    }
    public static function publicSeed(state:Object,context:Object):Array
    {
        var hash:Array = GwaiV8Hash.digest(GwaiV8Hash.canonical(GwaiV8Belief.publicPayload(state,context)));
        return [hash[1],hash[0]]; // Little-endian 32-bit limbs of the first eight bytes.
    }
    public static function increment(seed:Array,amount:int):Array
    {
        var words:Array = seed.slice(); var carry:Number = amount;
        for(var i:int = 0; carry > 0; ++i)
        {
            if(i == words.length) words.push(0);
            var sum:Number = Number(words[i])+carry; words[i] = uint(sum); carry = Math.floor(sum/4294967296.0);
        }
        return words;
    }
    public static function draw(state:Object,remaining:Array,prior:int,random:Object):int
    {
        var cumulative:Array = []; var total:int = 0;
        for(var i:int = 0; i < remaining.length; ++i)
        {
            var creature:Boolean = GwaiV8Position.isType(state.catalog[remaining[i]],8);
            total += prior == 0 ? 1 : prior == 1 ? (creature ? 3 : 1) : (creature ? 1 : 3); cumulative.push(total);
        }
        var chosen:Number = random.random()*total; var index:int = 0;
        while(index < cumulative.length-1 && chosen >= cumulative[index]) ++index;
        return remaining.splice(index,1)[0];
    }
    public static function hypotheses(state:Object,context:Object,samples:int = 4):Array
    {
        if(samples < 1) throw new Error("at least one hypothesis is required");
        var other:int = 1-state.player; var seen:Object = {}; var key:String; var template:int; var card:Object;
        for(key in state.cards)
        {
            card = state.cards[key]; if(card.owner == other) seen[card.template] = int(seen[card.template])+1;
        }
        var templates:Array = []; for(key in state.catalog) templates.push(int(key)); templates.sort(Array.NUMERIC);
        var pool:Array = [];
        for(var i:int = 0; i < templates.length; ++i)
        {
            template = templates[i]; card = state.catalog[template];
            if(card.faction != 0 && card.faction != context.opponent_faction) continue;
            if(!GwaiV8Position.isType(card,8) && !GwaiV8Position.isType(card,16) && !GwaiV8Position.isType(card,32) && !GwaiV8Position.isType(card,64)) continue;
            var cap:int = GwaiV8Position.isType(card,128) ? 1 : 3;
            for(var copy:int = 0; copy < Math.max(0,cap-int(seen[template])); ++copy) pool.push(template);
        }
        if(pool.length < context.opponent_hand_count) return [];
        var seed:Array = GwaiV8Belief.publicSeed(state,context); var out:Array = [];
        for(var index:int = 0; index < samples; ++index)
        {
            var random:Object = new GwaiV8Random(GwaiV8Belief.increment(seed,index)); var remaining:Array = pool.slice(); var selected:Array = [];
            var unsupported:int = 0; var prior:int = index%3;
            for(var slot:int = 0; slot < context.opponent_hand_count; ++slot)
            {
                template = GwaiV8Belief.draw(state,remaining,prior,random); card = GwaiV8Position.copyMap(state.catalog[template]);
                card.key = -200000000-index*1000-slot; card.owner = other; card.player = other; card.row = 1; card.applied = [];
                selected.push(card); if(!state.supported(card)) ++unsupported;
            }
            var counts:Object = {}; var count:int = Math.min(16,remaining.length);
            for(slot = 0; slot < count; ++slot) { template = GwaiV8Belief.draw(state,remaining,prior,random); counts[template] = int(counts[template])+1; }
            var ordered:Array = []; for(key in counts) ordered.push([int(key),counts[key]]); ordered.sort(GwaiV8Position.firstKeyOrder);
            out.push({hand:selected,counts:ordered,unsupported:unsupported,prior:["balanced","unit-heavy","special-heavy"][prior]});
        }
        return out;
    }
    public static function opponentView(state:Object,hypothesis:Object):Object
    {
        var view:Object = state.clone(); view.player = 1-state.player; view.hand = []; view.counts = {};
        for(var i:int = 0; i < hypothesis.hand.length; ++i)
        { var card:Object = hypothesis.hand[i]; view.hand.push(card.key); view.cards[card.key] = card; }
        for(i = 0; i < hypothesis.counts.length; ++i) view.counts[hypothesis.counts[i][0]] = hypothesis.counts[i][1];
        view.unknown_draws = 0; view.draw_value = 0; return view;
    }
}
