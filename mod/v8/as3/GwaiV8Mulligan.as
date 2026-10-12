// Original own-deck expected-hand-value mulligan, matching sim/mulligan_policy.py.
// Uniform prior over the own remaining templates; the shuffled order is never read.
internal class GwaiV8Mulligan
{
    public static const ROWS:Array = [5,4,3];
    public static const ROW_FLAGS:Object = {5:1,4:2,3:4};

    public static function retemplate(target:Object, card:Object, player:int):Object
    {
        var out:Object = GwaiV8Mulligan.copy(target);
        out.key = card.key; out.owner = player; out.player = player; out.row = 1; out.applied = [];
        return out;
    }
    public static function copy(card:Object):Object
    {
        var out:Object = {};
        for(var name:String in card) out[name] = card[name];
        return out;
    }
    public static function exchanged(state:GwaiV8Position, source:int, template:int):GwaiV8Position
    {
        var out:GwaiV8Position = state.clone(); var old:Object = out.cards[source];
        out.counts[template] = int(out.counts[template])-1;
        out.counts[old.template] = int(out.counts[old.template] || 0)+1;
        out.cards[source] = GwaiV8Mulligan.retemplate(state.catalog[template],{key:source},state.player);
        return out;
    }
    public static function spyAdjustment(state:GwaiV8Position):Number
    {
        var total:int = 0; var sum:Number = 0; var key:Object;
        for(key in state.counts) { total += int(state.counts[key]); sum += state.catalog[key].power*int(state.counts[key]); }
        var available:int = Math.max(0,total-state.unknown_draws);
        var mean:Number = total > 0 ? sum/total : 0;
        var old:Number = 0; var costs:Array = []; var i:int; var j:int;
        for(i = 0; i < state.hand.length; ++i)
        {
            var card:Object = state.cards[state.hand[i]];
            if(!GwaiV8Position.isType(card,256) || !GwaiV8Position.has(card,34)) continue;
            var weight:Number = Math.max(card.power,0);
            for(j = 0; j < card.effects.length; ++j) weight = Math.max(weight,Number(state.weights[card.effects[j]] || 0));
            old += weight;
            costs.push(card.power*(state.double_spy && !GwaiV8Position.isType(card,128) ? 2 : 1));
        }
        costs.sort(Array.NUMERIC);
        var value:Number = 0;
        for(i = 0; i < costs.length; ++i)
        {
            var drawn:int = Math.min(2,available); var gain:Number = drawn*mean-costs[i];
            if(gain > 0) { value += gain; available -= drawn; }
        }
        return value-old;
    }
    public static function potential(state:GwaiV8Position):Number
    {
        var cards:Array = []; var mushrooms:Array = []; var choices:Array = []; var i:int; var j:int; var r:int;
        for(i = 0; i < state.hand.length; ++i) cards.push(state.cards[state.hand[i]]);
        for(i = 0; i < cards.length; ++i)
            if(GwaiV8Position.has(cards[i],41))
            {
                mushrooms.push(cards[i]); var rows:Array = [-1];
                for(r = 0; r < ROWS.length; ++r) if(GwaiV8Position.isType(cards[i],ROW_FLAGS[ROWS[r]])) rows.push(ROWS[r]);
                choices.push(rows);
            }
        var best:Number = Number.NEGATIVE_INFINITY;
        var pick:Array = []; for(i = 0; i < choices.length; ++i) pick.push(0);
        while(true)
        {
            var assignment:Array = []; for(i = 0; i < choices.length; ++i) assignment.push(choices[i][pick[i]]);
            best = Math.max(best,GwaiV8Mulligan.assigned(state,cards,mushrooms,assignment));
            // Odometer in itertools.product order: the last position changes fastest.
            for(i = choices.length-1; i >= 0; --i)
            {
                if(++pick[i] < choices[i].length) break;
                pick[i] = 0;
            }
            if(i < 0) break;
        }
        return best;
    }
    public static function assigned(state:GwaiV8Position, cards:Array, mushrooms:Array, assignment:Array):Number
    {
        var out:GwaiV8Position = state.clone(); var active:Object = {}; var occupied:Object = {};
        var slots:int = 0; var distinct:int = 0; var i:int; var r:int; var card:Object; var row:int;
        for(i = 0; i < assignment.length; ++i) if(assignment[i] >= 0) active[assignment[i]] = true;
        for(i = 0; i < mushrooms.length; ++i)
            if(assignment[i] >= 0 && GwaiV8Position.isType(mushrooms[i],64))
            {
                ++slots; if(!occupied[assignment[i]]) { occupied[assignment[i]] = true; ++distinct; }
            }
        // Two row modifiers cannot be deployed in the same slot.
        if(slots != distinct) return Number.NEGATIVE_INFINITY;
        for(i = 0; i < mushrooms.length; ++i)
        {
            card = mushrooms[i]; row = assignment[i];
            if(GwaiV8Position.isType(card,64)) out.hand = GwaiV8Position.without(out.hand,card.key);
            else if(row >= 0)
            {
                var changed:Object = GwaiV8Mulligan.copy(card);
                changed.types = (card.types & ~7) | ROW_FLAGS[row];
                changed.effects = []; for(r = 0; r < card.effects.length; ++r) if(card.effects[r] != 41) changed.effects.push(card.effects[r]);
                out.cards[card.key] = changed;
            }
        }
        for(i = 0; i < cards.length; ++i)
        {
            card = cards[i]; var target:Object = null;
            if(card.targets.length == 1 && state.catalog[card.targets[0]] != null)
            {
                if(GwaiV8Position.has(card,40)) target = state.catalog[card.targets[0]];
                else if(GwaiV8Position.has(card,42))
                {
                    var flags:int = 0; var any:Boolean = false;
                    for(r = 0; r < ROWS.length; ++r)
                        if(active[ROWS[r]] && GwaiV8Position.isType(card,ROW_FLAGS[ROWS[r]])) { flags |= ROW_FLAGS[ROWS[r]]; any = true; }
                    if(any)
                    {
                        target = GwaiV8Mulligan.copy(state.catalog[card.targets[0]]);
                        target.types = (target.types & ~7) | flags;
                    }
                }
            }
            if(target != null) out.cards[card.key] = GwaiV8Mulligan.retemplate(target,card,state.player);
            if(GwaiV8Position.isType(card,64) && GwaiV8Position.has(card,27))
            {
                var horn:Object = GwaiV8Mulligan.copy(card);
                for(var key:Object in occupied) horn.types &= ~ROW_FLAGS[key];
                out.cards[card.key] = horn;
            }
        }
        // The plain reserve, as in the Lab's mulligan (Mushroom rows are enumerated above).
        return GwaiV8Reserve.reserve(out)+GwaiV8Mulligan.spyAdjustment(out);
    }
    // A leader that pulls a weather card from the deck (Frost 13, Fog 12, Rain 11): that weather
    // in hand goes back first (Lab: proven gain); otherwise the evaluated exchange.
    public static const LEADER_PICK:Object = {13:23,12:24,11:25};
    public static function chooseWithLeader(state:GwaiV8Position, leaderEffect:int):int
    {
        var weather:Object = LEADER_PICK[leaderEffect];
        if(weather != null)
            for(var i:int = 0; i < state.hand.length; ++i)
            {
                var card:Object = state.cards[state.hand[i]];
                if(card.effects.length > 0 && card.effects[0] == weather) return state.hand[i];
            }
        return GwaiV8Mulligan.choose(state);
    }
    // Greedy: one positive expected-value exchange, recomputed after the real draw.
    // Returns the hand key to exchange, or -1 to keep the hand.
    public static function choose(state:GwaiV8Position):int
    {
        var templates:Array = []; var total:int = 0; var key:Object;
        for(key in state.counts) if(int(state.counts[key]) > 0) { templates.push(int(key)); total += int(state.counts[key]); }
        if(total == 0 || state.hand.length == 0) return -1;
        templates.sort(Array.NUMERIC);
        var best:Number = GwaiV8Mulligan.potential(state); var source:int = -1;
        for(var i:int = 0; i < state.hand.length; ++i)
        {
            var sum:Number = 0;
            for(var j:int = 0; j < templates.length; ++j)
                sum += int(state.counts[templates[j]])*GwaiV8Mulligan.potential(GwaiV8Mulligan.exchanged(state,state.hand[i],templates[j]));
            var expected:Number = sum/total;
            if(expected > best+1e-9) { best = expected; source = state.hand[i]; }
        }
        return source;
    }
}
