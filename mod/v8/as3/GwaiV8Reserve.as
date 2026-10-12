// Original bounded own/public reserve evaluation, matching Python future_value.
// This estimates potential after a normal board clear, never a hidden draw order.
internal class GwaiV8Reserve
{
    public static function cardRows(card:Object):Array
    {
        var out:Array = []; var flags:Array = [1,2,4];
        for(var i:int = 0; i < flags.length; ++i) if(GwaiV8Position.isType(card,flags[i])) out.push(i);
        return out;
    }
    public static function describe(card:Object, legalRows:Array = null):Object
    {
        return {key:card.key,template:card.template,power:card.power,rows:legalRows == null ? GwaiV8Reserve.cardRows(card) : legalRows,
            hero:GwaiV8Position.isType(card,128),morale:false,bond:false,bond_targets:card.targets,
            horn:false,unsupported_value:0,summons:[]};
    }
    public static function power(input:Array):Number
    {
        // Preserve insertion order, including replacements of duplicate input keys.
        var cards:Array = []; var indices:Object = {}; var i:int; var j:int; var card:Object; var key:String;
        for(i = 0; i < input.length; ++i)
        {
            card = input[i]; key = String(card.key);
            if(indices[key] == null) { indices[key] = cards.length; cards.push(card); }
            else cards[indices[key]] = card;
        }
        for(i = 0; i < input.length; ++i)
            for(j = 0; j < input[i].summons.length; ++j)
            {
                card = input[i].summons[j]; key = String(card.key);
                if(indices[key] == null) { indices[key] = cards.length; cards.push(card); }
            }
        var units:Array = []; var horns:Array = []; var extra:Number = 0; var synergy:Boolean = false;
        for(i = 0; i < cards.length; ++i)
        {
            card = cards[i]; extra += card.unsupported_value;
            if(card.horn) horns.push(card);
            else if(card.rows.length > 0) { units.push(card); synergy = synergy || card.morale || card.bond; }
        }
        if(horns.length == 0 && !synergy)
        {
            for(i = 0; i < units.length; ++i) extra += units[i].power;
            return extra;
        }
        var choices:Array = []; for(i = 0; i < units.length; ++i) choices.push(0);
        var maximum:Number = 0; var done:Boolean = false;
        for(var iteration:int = 0; iteration < 4096 && !done; ++iteration)
        {
            var totals:Array = [0,0,0]; var gains:Array = [0,0,0];
            for(i = 0; i < units.length; ++i)
            {
                card = units[i]; var row:int = card.rows[choices[i]]; var value:Number = card.power;
                if(!card.hero)
                {
                    var morale:int = 0; var bonds:int = 0;
                    for(j = 0; j < units.length; ++j)
                        if(units[j].rows[choices[j]] == row && units[j].key != card.key)
                        {
                            if(units[j].morale) ++morale;
                            if(units[j].bond && units[j].bond_targets.indexOf(card.template) >= 0) ++bonds;
                        }
                    value = card.power*(1+bonds)+morale; gains[row] += value;
                }
                totals[row] += value;
            }
            var reachable:Array = [true,false,false,false,false,false,false,false];
            for(i = 0; i < horns.length; ++i)
            {
                var previous:Array = reachable.slice();
                for(var mask:int = 0; mask < 8; ++mask)
                    if(previous[mask])
                        for(j = 0; j < horns[i].rows.length; ++j)
                        {
                            row = horns[i].rows[j];
                            if((mask & (1 << row)) == 0) reachable[mask | (1 << row)] = true;
                        }
            }
            var hornBest:Number = 0;
            for(mask = 0; mask < 8; ++mask)
                if(reachable[mask])
                {
                    value = 0;
                    for(row = 0; row < 3; ++row) if((mask & (1 << row)) != 0) value += gains[row];
                    hornBest = Math.max(hornBest,value);
                }
            maximum = Math.max(maximum,totals[0]+totals[1]+totals[2]+hornBest);
            // Same order as itertools.product: the rightmost index changes first.
            done = true;
            for(i = choices.length-1; i >= 0; --i)
            {
                ++choices[i];
                if(choices[i] < units[i].rows.length) { done = false; break; }
                choices[i] = 0;
            }
        }
        return maximum+extra;
    }
    public static function recoverySimple(card:Object):Boolean
    {
        return GwaiV8Position.isType(card,8) && !GwaiV8Position.isType(card,128) && !GwaiV8Position.isType(card,256)
            && GwaiV8Position.subset(card.effects,[0,32,35,31,33]);
    }
    public static function recoverable(state:Object, side:int):Array
    {
        var keys:Array = state.grave[side].slice(); var out:Array = [];
        for(var r:int = 0; r < 3; ++r) keys = keys.concat(state.board[GwaiV8Position.slot(side,GwaiV8Position.ROWS[r])]);
        for(var i:int = 0; i < keys.length; ++i)
            if(GwaiV8Reserve.recoverySimple(state.cards[keys[i]])) out.push(state.cards[keys[i]]);
        return out;
    }
    public static function recoveryOrder(a:Object,b:Object):Number
    { return a.power == b.power ? a.key-b.key : b.power-a.power; }
    public static function recovery(state:Object, medics:int):Array
    {
        var out:Array = []; if(medics == 0 || state.random_recovery) return out;
        var pool:Array = GwaiV8Reserve.recoverable(state,state.player); var nurses:Array = []; var units:Array = [];
        for(var i:int = 0; i < pool.length; ++i)
            if(GwaiV8Position.has(pool[i],33)) nurses.push(pool[i]); else units.push(pool[i]);
        units.sort(recoveryOrder); pool = nurses.concat(units.slice(0,medics));
        for(i = 0; i < pool.length; ++i)
        {
            var card:Object = pool[i]; var value:Object = GwaiV8Reserve.describe(card);
            value.morale = GwaiV8Position.has(card,32); value.bond = GwaiV8Position.has(card,35); value.hero = false;
            out.push(value);
        }
        return out;
    }
    public static function leader(state:Object):Object
    {
        var out:Object = {cards:[],recoveries:0}; var side:int = state.player;
        if(!state.leaderModeled(side)) return out;
        var effect:int = state.leaderEffect(side); var key:int = state.leaders[side]; var row:int = GwaiV8Position.leaderHornRow(effect);
        var value:Object = GwaiV8Reserve.describe(state.cards[key],[]); value.template = 0; value.power = 0; value.hero = false;
        if(row > 0)
        {
            value.template = 1; value.rows = [row == 5 ? 0 : row == 4 ? 1 : 2]; value.horn = true;
            // A row Mushroom kept for later takes that row's modifier slot (mushroomReserve).
            if(GwaiV8Reserve.blocked != null && GwaiV8Reserve.blocked.indexOf(value.rows[0]) >= 0) value.rows = [];
            out.cards.push(value);
        }
        else if(effect == 15) out.recoveries = 1;
        else if(effect == 16)
        {
            var pool:Array = GwaiV8Reserve.recoverable(state,1-side); pool.sort(recoveryOrder);
            if(pool.length > 0)
            {
                value = GwaiV8Reserve.describe(pool[0]); value.morale = false; value.bond = false; out.cards.push(value);
            }
        }
        else
        {
            if(GwaiV8Position.leaderScorchRow(effect) > 0) value.unsupported_value = Number(state.weights[29] || 0);
            else if([9,10,11,12,13].indexOf(effect) >= 0) value.unsupported_value = Number(state.weights.weather || 0);
            out.cards.push(value);
        }
        return out;
    }
    public static var blocked:Array = null;
    // Python keeps a set of (frozenset active, frozenset occupied, units tuple) states.
    public static function addState(following:Array, seen:Object, n:Object):void
    {
        var k:String = n.active.slice().sort(Array.NUMERIC).join(",")+"|"+n.occupied.slice().sort(Array.NUMERIC).join(",")+"|"+n.units.join(",");
        if(!seen[k]) { seen[k] = true; following.push(n); }
    }
    // Held Mushroom + Berserker combinations after a normal clear (sim/mushroom_reserve.py): the
    // best inherited ceiling over the Mushroom row choices; the plain reserve otherwise.
    public static function mushroomReserve(state:Object):Number
    {
        var reference:Number = GwaiV8Reserve.reserve(state); var i:int; var j:int; var r:int;
        var rowsOrder:Array = [5,4,3]; var flags:Object = {5:1,4:2,3:4};
        var cards:Array = []; for(i = 0; i < state.hand.length; ++i) cards.push(state.cards[state.hand[i]]);
        var morphs:Array = []; var shrooms:Array = []; var shroomKeys:Object = {};
        for(i = 0; i < cards.length; ++i)
        {
            if(GwaiV8Position.has(cards[i],GwaiV8Const.CardEffect_Morph) && state.supported(cards[i])) morphs.push(cards[i]);
            if(GwaiV8Position.only(cards[i].effects,GwaiV8Const.CardEffect_Mushroom) && state.supported(cards[i])) { shrooms.push(cards[i]); shroomKeys[cards[i].key] = true; }
        }
        if(morphs.length == 0 || shrooms.length == 0) return reference;
        var relevant:Object = {};
        for(i = 0; i < morphs.length; ++i) for(r = 0; r < 3; ++r) if(GwaiV8Position.isType(morphs[i],flags[rowsOrder[r]])) relevant[rowsOrder[r]] = true;
        var states:Array = [{active:[],occupied:[],units:[]}]; var seen:Object = {};
        for(i = 0; i < shrooms.length; ++i)
        {
            var card:Object = shrooms[i]; var choices:Array = [];
            for(r = 0; r < 3; ++r) if(relevant[rowsOrder[r]] && GwaiV8Position.isType(card,flags[rowsOrder[r]])) choices.push(rowsOrder[r]);
            var following:Array = []; seen = {};
            for(j = 0; j < states.length; ++j)
            {
                var s:Object = states[j];
                GwaiV8Reserve.addState(following,seen,s);
                for(r = 0; r < choices.length; ++r)
                {
                    var row:int = choices[r];
                    var active:Array = s.active.indexOf(row) >= 0 ? s.active : s.active.concat([row]);
                    if(GwaiV8Position.isType(card,64)) { if(s.occupied.indexOf(row) < 0) GwaiV8Reserve.addState(following,seen,{active:active,occupied:s.occupied.concat([row]),units:s.units}); }
                    else GwaiV8Reserve.addState(following,seen,{active:active,occupied:s.occupied,units:s.units.concat([card.key+":"+row])});
                }
            }
            if(following.length > 4096) return reference;   // conservative bound for huge hands
            states = following;
        }
        var best:Number = reference;
        for(j = 0; j < states.length; ++j)
        {
            var st:Object = states[j]; if(st.active.length == 0) continue;
            var view:Object = state.clone(); var hand:Array = [];
            for(i = 0; i < view.hand.length; ++i)
                if(!(shroomKeys[view.hand[i]] && GwaiV8Position.isType(view.cards[view.hand[i]],64))) hand.push(view.hand[i]);
            view.hand = hand;
            for(i = 0; i < st.units.length; ++i)
            {
                var pair:Array = st.units[i].split(":"); var unit:Object = GwaiV8Position.copyMap(view.cards[int(pair[0])]);
                unit.types = (unit.types & ~7) | flags[int(pair[1])]; unit.effects = [0]; view.cards[unit.key] = unit;
            }
            for(i = 0; i < morphs.length; ++i)
            {
                var mask:int = 0;
                for(r = 0; r < st.active.length; ++r) if(GwaiV8Position.isType(morphs[i],flags[st.active[r]])) mask |= flags[st.active[r]];
                if(mask == 0) continue;
                var bear:Object = GwaiV8Position.copyMap(state.catalog[morphs[i].targets[0]]);
                bear.key = morphs[i].key; bear.owner = morphs[i].owner; bear.player = morphs[i].player; bear.row = 1; bear.applied = [];
                bear.types = (bear.types & ~7) | mask; view.cards[bear.key] = bear;
            }
            for(i = 0; i < cards.length; ++i)
                if(GwaiV8Position.isType(cards[i],64) && GwaiV8Position.has(cards[i],GwaiV8Const.CardEffect_Horn))
                {
                    var horn:Object = GwaiV8Position.copyMap(cards[i]);
                    for(r = 0; r < st.occupied.length; ++r) horn.types &= ~flags[st.occupied[r]];
                    view.cards[horn.key] = horn;
                }
            var blockedRows:Array = [];
            for(r = 0; r < 3; ++r) if(st.occupied.indexOf(rowsOrder[r]) >= 0) blockedRows.push(r);
            GwaiV8Reserve.blocked = blockedRows;
            try { best = Math.max(best,GwaiV8Reserve.reserve(view)); }
            finally { GwaiV8Reserve.blocked = null; }
        }
        return best;
    }
    public static function reserve(state:Object):Number
    {
        var out:Array = []; var medics:int = 0;
        for(var i:int = 0; i < state.hand.length; ++i)
        {
            var card:Object = state.cards[state.hand[i]];
            var nurse:Boolean = GwaiV8Position.has(card,33) && !(state.random_recovery && !GwaiV8Position.isType(card,128));
            if(nurse) ++medics;
            var allowed:Array = [0,32,35,31]; if(nurse) allowed.push(33);
            var simple:Boolean = GwaiV8Position.isType(card,8) && !GwaiV8Position.isType(card,256) && GwaiV8Position.subset(card.effects,allowed);
            var horn:Boolean = GwaiV8Position.isType(card,64) && GwaiV8Position.has(card,27);
            var value:Object = GwaiV8Reserve.describe(card,simple || horn ? GwaiV8Reserve.cardRows(card) : []);
            value.morale = simple && GwaiV8Position.has(card,32); value.bond = simple && GwaiV8Position.has(card,35); value.horn = horn;
            if(simple && GwaiV8Position.has(card,31) && state.unknown_draws == 0)
            {
                var targets:Array = []; var seen:Object = {};
                for(var j:int = 0; j < card.targets.length; ++j)
                    if(!seen[card.targets[j]]) { seen[card.targets[j]] = true; targets.push(card.targets[j]); }
                targets.sort(Array.NUMERIC);
                for(j = 0; j < targets.length; ++j)
                {
                    var template:int = targets[j]; var summoned:Object = state.catalog[template];
                    var safe:Boolean = GwaiV8Position.isType(summoned,8) && !GwaiV8Position.isType(summoned,256) && GwaiV8Position.subset(summoned.effects,[0,31]);
                    for(var index:int = 0; index < int(state.counts[template]); ++index)
                    {
                        var copy:Object = GwaiV8Reserve.describe(summoned,safe ? GwaiV8Reserve.cardRows(summoned) : []);
                        copy.key = -(template*10000+index+1); copy.unsupported_value = safe ? 0 : summoned.power;
                        value.summons.push(copy);
                    }
                }
            }
            if(!simple && !horn)
            {
                var weight:Number = Math.max(card.power,0);
                for(j = 0; j < card.effects.length; ++j) weight = Math.max(weight,Number(state.weights[card.effects[j]] || 0));
                if(GwaiV8Position.isType(card,16)) weight = Math.max(weight,Number(state.weights.weather));
                value.unsupported_value = weight;
            }
            out.push(value);
        }
        var kept:Object = GwaiV8Reserve.leader(state); if(kept.recoveries > 0 && !state.random_recovery) medics += kept.recoveries;
        return GwaiV8Reserve.power(out.concat(kept.cards,GwaiV8Reserve.recovery(state,medics)))+state.draw_value;
    }
}
