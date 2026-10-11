// Original detached own/public position model. Native card objects are never
// retained or mutated. Effects outside the supported transitions fail explicitly.
internal class GwaiV8Position
{
    public var player:int = 0;
    public var cards:Object = {};
    public var hand:Array = [];
    public var board:Object = {};
    public var grave:Object = {};
    public var effects:Object = {};
    public var counts:Object = {};
    public var catalog:Object = {};
    public var half_weather:Array = [false,false];
    public var double_spy:Boolean = false;
    public var random_recovery:Boolean = false;
    public var weights:Object = {};
    public var unknown_draws:int = 0;
    public var draw_value:Number = 0;
    public var next_key:int = -10000000;
    public var leaders:Object = {};
    public var leader_ready:Object = {};
    public static var ROWS:Array = [5,4,3];

    public static function isType(card:Object, flag:int):Boolean
    { return card != null && (int(card.types) & flag) == flag; }
    public static function has(card:Object, flag:int):Boolean
    { return card != null && card.effects.indexOf(flag) >= 0; }
    public static function slot(side:int, row:int):String
    { return side + ":" + row; }
    public static function rowFlag(row:int):int
    { return row == 5 ? 1 : row == 4 ? 2 : row == 3 ? 4 : -1; }
    public static function copyMap(source:Object):Object
    {
        var out:Object = {};
        for(var key:String in source) out[key] = source[key];
        return out;
    }
    public static function without(list:Array, key:int):Array
    {
        var out:Array = [];
        for(var i:int = 0; i < list.length; ++i) if(list[i] != key) out.push(list[i]);
        return out;
    }
    public static function action(source:int, row:int = -1, target:int = -1, chain:Array = null):Object
    { return {source:source,slot:row,target:target,chain:chain == null ? [] : chain}; }
    public static function subset(flags:Array, allowed:Array):Boolean
    {
        for(var i:int = 0; i < flags.length; ++i) if(allowed.indexOf(flags[i]) < 0) return false;
        return true;
    }
    public function clone():GwaiV8Position
    {
        var out:GwaiV8Position = new GwaiV8Position();
        out.player = player; out.cards = GwaiV8Position.copyMap(cards); out.hand = hand.slice();
        out.board = GwaiV8Position.copyMap(board); out.grave = GwaiV8Position.copyMap(grave); out.effects = GwaiV8Position.copyMap(effects);
        out.counts = GwaiV8Position.copyMap(counts); out.catalog = catalog; out.half_weather = half_weather;
        out.double_spy = double_spy; out.random_recovery = random_recovery; out.weights = weights;
        out.unknown_draws = unknown_draws; out.draw_value = draw_value; out.next_key = next_key;
        out.leaders = GwaiV8Position.copyMap(leaders); out.leader_ready = GwaiV8Position.copyMap(leader_ready);
        return out;
    }
    public function power(key:int):Number
    {
        var card:Object = cards[key];
        if(GwaiV8Position.isType(card,128)) return card.power;
        var weather:Boolean = false; var bond:int = 0; var morale:int = 0; var horn:Boolean = false;
        for(var i:int = 0; i < card.applied.length; ++i)
        {
            var effect:Object = cards[card.applied[i]];
            weather = weather || GwaiV8Position.isType(effect,16);
            if(GwaiV8Position.has(effect,GwaiV8Const.CardEffect_SameTypeMorale)) ++bond;
            if(GwaiV8Position.has(effect,GwaiV8Const.CardEffect_ImproveNeighbours)) ++morale;
            horn = horn || GwaiV8Position.has(effect,GwaiV8Const.CardEffect_Horn) || GwaiV8Position.has(effect,GwaiV8Const.CardEffect_Melee_Horn) || GwaiV8Position.has(effect,GwaiV8Const.CardEffect_Range_Horn) || GwaiV8Position.has(effect,GwaiV8Const.CardEffect_Siege_Horn);
        }
        var base:Number = card.power;
        if(weather) base = half_weather[card.player] ? Math.max(0,Math.floor(base/2)) : Math.min(1,base);
        if(GwaiV8Position.isType(card,256) && double_spy) base *= 2;
        var value:Number = base * (1+bond) + morale;
        return horn ? value*2 : value;
    }
    public function scores():Array
    {
        var out:Array = [0,0];
        for(var side:int = 0; side < 2; ++side)
            for(var r:int = 0; r < ROWS.length; ++r)
            {
                var units:Array = board[GwaiV8Position.slot(side,ROWS[r])];
                for(var i:int = 0; i < units.length; ++i) out[side] += power(units[i]);
            }
        return out;
    }
    public function supported(card:Object):Boolean
    {
        if(GwaiV8Position.has(card,GwaiV8Const.CardEffect_Nurse) && random_recovery && !GwaiV8Position.isType(card,128)) return false;
        if(GwaiV8Position.isType(card,8)) return GwaiV8Position.subset(card.effects,[GwaiV8Const.CardEffect_None,GwaiV8Const.CardEffect_ImproveNeighbours,GwaiV8Const.CardEffect_SameTypeMorale,GwaiV8Const.CardEffect_Horn,GwaiV8Const.CardEffect_SummonClones,GwaiV8Const.CardEffect_Draw2,GwaiV8Const.CardEffect_MeleeScorch,GwaiV8Const.CardEffect_RangedScorch,GwaiV8Const.CardEffect_Siege_Scorch,GwaiV8Const.CardEffect_Nurse]);
        if(GwaiV8Position.isType(card,64)) return GwaiV8Position.has(card,GwaiV8Const.CardEffect_Horn);
        return GwaiV8Position.isType(card,16) || GwaiV8Position.has(card,GwaiV8Const.CardEffect_Scorch) || GwaiV8Position.has(card,GwaiV8Const.CardEffect_UnsummonDummy);
    }
    public function recoveryTargets(side:int, taken:Array = null):Array
    {
        if(taken == null) taken = [];
        var out:Array = []; var list:Array = grave[side];
        for(var i:int = 0; i < list.length; ++i)
            if(taken.indexOf(list[i]) < 0 && GwaiV8Position.isType(cards[list[i]],8) && !GwaiV8Position.isType(cards[list[i]],128)) out.push(list[i]);
        return out;
    }
    public function recoveryChains(side:int, taken:Array = null):Array
    {
        if(taken == null) taken = [];
        var eligible:Array = recoveryTargets(side,taken);
        if(eligible.length == 0) return [[]];
        var out:Array = []; var seen:Object = {};
        for(var i:int = eligible.length-1; i >= 0; --i)
        {
            var key:int = eligible[i]; var card:Object = cards[key];
            if(seen[card.template]) continue;
            seen[card.template] = true;
            if(!supported(card)) continue;
            var rest:Array = GwaiV8Position.has(card,GwaiV8Const.CardEffect_Nurse) ? recoveryChains(side,taken.concat([key])) : [[]];
            for(var r:int = 0; r < ROWS.length; ++r)
                if(GwaiV8Position.isType(card,GwaiV8Position.rowFlag(ROWS[r])))
                    for(var t:int = 0; t < rest.length; ++t) out.push([[key,ROWS[r]]].concat(rest[t]));
        }
        return out;
    }
    public function cardActions():Array
    {
        var out:Array = [];
        for(var i:int = 0; i < hand.length; ++i)
        {
            var key:int = hand[i]; var card:Object = cards[key];
            if(!supported(card)) continue;
            if(GwaiV8Position.has(card,GwaiV8Const.CardEffect_UnsummonDummy))
            {
                for(var r:int = 0; r < ROWS.length; ++r)
                {
                    var list:Array = board[GwaiV8Position.slot(player,ROWS[r])];
                    for(var t:int = 0; t < list.length; ++t)
                        if(GwaiV8Position.isType(cards[list[t]],8) && !GwaiV8Position.isType(cards[list[t]],128)) out.push(GwaiV8Position.action(key,-1,list[t]));
                }
            }
            else if(GwaiV8Position.isType(card,8))
            {
                var chains:Array = GwaiV8Position.has(card,GwaiV8Const.CardEffect_Nurse) ? recoveryChains(player) : [[]];
                for(r = 0; r < ROWS.length; ++r)
                    if(GwaiV8Position.isType(card,GwaiV8Position.rowFlag(ROWS[r])))
                        for(t = 0; t < chains.length; ++t) out.push(GwaiV8Position.action(key,ROWS[r],-1,chains[t]));
            }
            else if(GwaiV8Position.isType(card,64))
            {
                for(r = 0; r < ROWS.length; ++r)
                    if(GwaiV8Position.isType(card,GwaiV8Position.rowFlag(ROWS[r])) && board[GwaiV8Position.slot(player,ROWS[r]+3)].length == 0)
                        out.push(GwaiV8Position.action(key,ROWS[r]+3));
            }
            else if(GwaiV8Position.isType(card,16)) out.push(GwaiV8Position.action(key,9));
            else if(GwaiV8Position.has(card,GwaiV8Const.CardEffect_Scorch)) out.push(GwaiV8Position.action(key));
        }
        return out;
    }
    public function addEffect(target:int, source:int):void
    {
        var card:Object = GwaiV8Position.copyMap(cards[target]);
        card.applied = card.applied.concat([source]); cards[target] = card;
    }
    public function removeEffect(key:int):void
    {
        for(var target:String in cards)
            if(cards[target].applied.indexOf(key) >= 0)
            {
                var card:Object = GwaiV8Position.copyMap(cards[target]); card.applied = GwaiV8Position.without(card.applied,key); cards[target] = card;
            }
        for(var loc:String in effects) effects[loc] = GwaiV8Position.without(effects[loc],key);
    }
    public function removeFromBoard(key:int, toGrave:Boolean = true):void
    {
        var card:Object = cards[key]; board[GwaiV8Position.slot(card.player,card.row)] = GwaiV8Position.without(board[GwaiV8Position.slot(card.player,card.row)],key);
        removeEffect(key);
        if(toGrave)
        {
            var destination:int = GwaiV8Position.isType(card,16) ? card.owner : card.player;
            grave[destination] = grave[destination].concat([key]);
            card = GwaiV8Position.copyMap(card); card.player = destination; card.row = 2; card.applied = []; cards[key] = card;
        }
    }
    public static function defaultRow(card:Object):int
    {
        for(var i:int = 0; i < ROWS.length; ++i) if(GwaiV8Position.isType(card,GwaiV8Position.rowFlag(ROWS[i]))) return ROWS[i];
        return -1;
    }
    public function totalCounts():int
    {
        var out:int = 0;
        for(var t:String in counts) out += counts[t];
        return out;
    }
    public function placeUnit(key:int, row:int, side:int, chain:Array = null):void
    {
        if(chain == null) chain = [];
        var card:Object = cards[key];
        if(!supported(card)) throw new GwaiV8Unsupported("summoned/recovered effect");
        var placed:Object = GwaiV8Position.copyMap(card); placed.player = side; placed.row = row;
        placed.applied = effects[GwaiV8Position.slot(side,row)].slice(); cards[key] = placed;
        var existing:Array = board[GwaiV8Position.slot(side,row)]; board[GwaiV8Position.slot(side,row)] = existing.concat([key]);
        if(GwaiV8Position.has(card,GwaiV8Const.CardEffect_ImproveNeighbours) || GwaiV8Position.has(card,GwaiV8Const.CardEffect_Horn))
        {
            for(var i:int = 0; i < existing.length; ++i)
                if(!GwaiV8Position.isType(cards[existing[i]],128) && !GwaiV8Position.has(cards[existing[i]],GwaiV8Const.CardEffect_UnsummonDummy)) addEffect(existing[i],key);
            effects[GwaiV8Position.slot(side,row)] = effects[GwaiV8Position.slot(side,row)].concat([key]);
        }
        if(GwaiV8Position.has(card,GwaiV8Const.CardEffect_SameTypeMorale))
            for(i = 0; i < existing.length; ++i)
                if(card.targets.indexOf(cards[existing[i]].template) >= 0 && !GwaiV8Position.isType(cards[existing[i]],128))
                { addEffect(existing[i],key); addEffect(key,existing[i]); }
        var burns:Array = [[GwaiV8Const.CardEffect_MeleeScorch,5],[GwaiV8Const.CardEffect_RangedScorch,4],[GwaiV8Const.CardEffect_Siege_Scorch,3]];
        for(i = 0; i < burns.length; ++i)
            if(GwaiV8Position.has(card,burns[i][0]))
            {
                var enemyList:Array = board[GwaiV8Position.slot(1-side,burns[i][1])]; var sum:Number = 0;
                for(var j:int = 0; j < enemyList.length; ++j) sum += power(enemyList[j]);
                if(sum >= 10) scorch([1-side],[burns[i][1]]);
            }
        if(GwaiV8Position.has(card,GwaiV8Const.CardEffect_SummonClones))
        {
            if(unknown_draws != 0) throw new GwaiV8Unsupported("Muster after unresolved draws");
            for(i = 0; i < card.targets.length; ++i)
            {
                var template:int = card.targets[i]; var previous:Array = hand.slice();
                for(j = 0; j < previous.length; ++j)
                    if(hand.indexOf(previous[j]) >= 0 && cards[previous[j]].template == template)
                    { hand = GwaiV8Position.without(hand,previous[j]); placeUnit(previous[j],GwaiV8Position.defaultRow(cards[previous[j]]),side); }
                var count:int = counts[template] == null ? 0 : int(counts[template]); counts[template] = 0;
                for(j = 0; j < count; ++j)
                {
                    --next_key; var summoned:Object = GwaiV8Position.copyMap(catalog[template]);
                    summoned.key = next_key; summoned.owner = player; summoned.player = player;
                    cards[next_key] = summoned; placeUnit(next_key,GwaiV8Position.defaultRow(summoned),side);
                }
            }
        }
        if(GwaiV8Position.has(card,GwaiV8Const.CardEffect_Draw2))
        {
            if(1-side != player) throw new GwaiV8Unsupported("opponent draw identities");
            var total:int = totalCounts(); var draw:int = Math.min(2,Math.max(0,total-unknown_draws));
            unknown_draws += draw; var printed:Number = 0;
            for(var templateKey:String in counts) printed += catalog[templateKey].power * counts[templateKey];
            draw_value += total > 0 ? draw*printed/total : 0;
        }
        if(GwaiV8Position.has(card,GwaiV8Const.CardEffect_Nurse)) recover(side,chain);
        else if(chain.length > 0) throw new Error("chain on non-Medic");
    }
    public function recover(side:int, chain:Array):void
    {
        var eligible:Array = recoveryTargets(side);
        if(eligible.length == 0)
        {
            if(chain.length > 0) throw new Error("empty graveyard chain");
            return;
        }
        if(chain.length == 0) throw new GwaiV8Unsupported("Medic choice unspecified");
        var target:int = chain[0][0]; var row:int = chain[0][1]; var card:Object = cards[target];
        if(eligible.indexOf(target) < 0 || !GwaiV8Position.isType(card,GwaiV8Position.rowFlag(row))) throw new Error("illegal recovery");
        grave[side] = GwaiV8Position.without(grave[side],target);
        placeUnit(target,row,GwaiV8Position.isType(card,256) ? 1-side : side,chain.slice(1));
    }
    public function scorch(sides:Array = null, rows:Array = null):void
    {
        if(sides == null) sides = [0,1]; if(rows == null) rows = ROWS;
        var eligible:Array = []; var maximum:Number = -1;
        for(var s:int = 0; s < sides.length; ++s)
            for(var r:int = 0; r < rows.length; ++r)
            {
                var list:Array = board[GwaiV8Position.slot(sides[s],rows[r])];
                for(var i:int = 0; i < list.length; ++i)
                    if(!GwaiV8Position.isType(cards[list[i]],128) && GwaiV8Position.isType(cards[list[i]],8))
                    { eligible.push(list[i]); maximum = Math.max(maximum,power(list[i])); }
            }
        var targets:Array = [];
        for(i = 0; i < eligible.length; ++i) if(power(eligible[i]) == maximum) targets.push(eligible[i]);
        for(i = 0; i < targets.length; ++i)
            if(GwaiV8Position.has(cards[targets[i]],GwaiV8Const.CardEffect_SuicideSummon) || GwaiV8Position.has(cards[targets[i]],GwaiV8Const.CardEffect_Morph) || GwaiV8Position.has(cards[targets[i]],GwaiV8Const.CardEffect_Mushroom))
                throw new GwaiV8Unsupported("death summons");
        for(i = 0; i < targets.length; ++i) removeFromBoard(targets[i]);
    }
    public function placeModifier(card:Object, loc:int, side:int):void
    {
        var row:int = loc-3; var placed:Object = GwaiV8Position.copyMap(card);
        placed.row = loc; placed.player = side; placed.applied = []; cards[card.key] = placed;
        board[GwaiV8Position.slot(side,loc)] = board[GwaiV8Position.slot(side,loc)].concat([card.key]);
        effects[GwaiV8Position.slot(side,row)] = effects[GwaiV8Position.slot(side,row)].concat([card.key]);
        var list:Array = board[GwaiV8Position.slot(side,row)];
        for(var i:int = 0; i < list.length; ++i) if(!GwaiV8Position.isType(cards[list[i]],128)) addEffect(list[i],card.key);
    }
    public function playWeather(card:Object):void
    {
        var current:Array = board[GwaiV8Position.slot(-1,9)].slice(); var i:int;
        if(GwaiV8Position.has(card,GwaiV8Const.CardEffect_ClearSky))
        {
            for(i = 0; i < current.length; ++i) removeFromBoard(current[i]);
            var cleared:Object = GwaiV8Position.copyMap(card); cleared.row = 2; cleared.applied = []; cards[card.key] = cleared;
            grave[card.owner] = grave[card.owner].concat([card.key]); return;
        }
        if(card.effects.length > 1)
        {
            for(i = 0; i < current.length; ++i)
            {
                var previous:Object = cards[current[i]];
                if(previous.template == card.template || (previous.effects.length > 0 && card.effects.indexOf(previous.effects[0]) >= 0))
                    removeFromBoard(current[i]);
            }
        }
        else
            for(i = 0; i < current.length; ++i)
                if(card.effects.length > 0 && GwaiV8Position.has(cards[current[i]],card.effects[0]))
                {
                    cleared = GwaiV8Position.copyMap(card); cleared.row = 2; cleared.applied = []; cards[card.key] = cleared;
                    grave[card.owner] = grave[card.owner].concat([card.key]); return;
                }
        var placed:Object = GwaiV8Position.copyMap(card); placed.row = 9; placed.player = -1; placed.applied = []; cards[card.key] = placed;
        board[GwaiV8Position.slot(-1,9)] = board[GwaiV8Position.slot(-1,9)].concat([card.key]);
        var weather:Array = [[GwaiV8Const.CardEffect_Melee,5],[GwaiV8Const.CardEffect_Ranged,4],[GwaiV8Const.CardEffect_Siege,3]];
        for(i = 0; i < weather.length; ++i)
            if(GwaiV8Position.has(card,weather[i][0]))
                for(var side:int = 0; side < 2; ++side)
                {
                    var row:int = weather[i][1]; effects[GwaiV8Position.slot(side,row)] = effects[GwaiV8Position.slot(side,row)].concat([card.key]);
                    var list:Array = board[GwaiV8Position.slot(side,row)];
                    for(var j:int = 0; j < list.length; ++j) if(!GwaiV8Position.isType(cards[list[j]],128)) addEffect(list[j],card.key);
                }
    }
    public function reserve():Number
    { return GwaiV8Reserve.reserve(this); }
    public function recoveryRelevant():Boolean
    {
        var effect:int = leaderModeled(player) ? leaderEffect(player) : -1;
        if(effect == 15 || effect == 16) return true;
        for(var i:int = 0; i < hand.length; ++i) if(GwaiV8Position.has(cards[hand[i]],33)) return true;
        return false;
    }
    public static function firstKeyOrder(a:Array,b:Array):Number
    { return a[0]-b[0]; }
    public function reserveKey():String
    {
        var held:Array = []; var remaining:Array = []; var recovery:Array = [];
        for(var i:int = 0; i < hand.length; ++i) held.push([hand[i],cards[hand[i]].template]);
        held.sort(firstKeyOrder);
        for(var key:String in counts) remaining.push([int(key),counts[key]]);
        remaining.sort(firstKeyOrder);
        if(recoveryRelevant())
        {
            var rows:Array = [];
            for(var side:int = 0; side < 2; ++side)
                for(var r:int = 0; r < ROWS.length; ++r) rows.push(board[GwaiV8Position.slot(side,ROWS[r])]);
            recovery = [grave[0],grave[1],rows];
        }
        return GwaiV8Hash.text([player,held,remaining,unknown_draws,draw_value,leaderModeled(player),recovery]);
    }
    public function leaderEffect(side:int):int
    {
        var key:Object = leaders[side]; var card:Object = key == null ? null : cards[key];
        return card == null || card.effects.length == 0 ? -1 : card.effects[0];
    }
    public function leaderModeled(side:int):Boolean
    {
        var effect:int = leaderEffect(side);
        return Boolean(leader_ready[side]) && [7,9,10,11,12,13,14,15,16,18,19,20,21,36,39,44].indexOf(effect) >= 0
            && !(random_recovery && (effect == 15 || effect == 16));
    }
    public function leaderUnmodeled(side:int):Boolean
    { return Boolean(leader_ready[side]) && [8,22,37,38,43].indexOf(leaderEffect(side)) < 0 && !leaderModeled(side); }
    public static function leaderHornRow(effect:int):int
    { return effect == 18 ? 5 : effect == 19 ? 4 : effect == 20 ? 3 : -1; }
    public static function leaderScorchRow(effect:int):int
    { return effect == 7 ? 5 : effect == 39 ? 4 : effect == 21 ? 3 : -1; }
    public function weatherTemplates(required:int = -1, excluded:int = -1):Array
    {
        var out:Array = [];
        for(var key:String in counts)
        {
            var card:Object = catalog[key];
            if(counts[key] > 0 && GwaiV8Position.isType(card,16) && !GwaiV8Position.has(card,30)
                && (required < 0 || GwaiV8Position.has(card,required)) && (excluded < 0 || !GwaiV8Position.has(card,excluded))) out.push(int(key));
        }
        out.sort(Array.NUMERIC); return out;
    }
    public function agileUnit(key:int):Boolean
    { return GwaiV8Position.isType(cards[key],8) && !GwaiV8Position.isType(cards[key],128) && GwaiV8Position.isType(cards[key],3); }
    public function repositionGain(key:int):Number
    {
        var card:Object = cards[key]; var other:int = card.row == 5 ? 4 : 5;
        var moved:GwaiV8Position = clone(); var changed:Object = GwaiV8Position.copyMap(card);
        changed.applied = effects[GwaiV8Position.slot(card.player,other)]; moved.cards[key] = changed;
        return Math.max(0,moved.power(key)-power(key));
    }
    public function leaderActions():Array
    {
        var side:int = player; var out:Array = [];
        if(!leaderModeled(side)) return out;
        var key:int = leaders[side]; var effect:int = leaderEffect(side); var enemy:int = 1-side;
        var row:int = GwaiV8Position.leaderHornRow(effect); var target:int; var i:int; var options:Array;
        if(row > 0) return board[GwaiV8Position.slot(side,row+3)].length == 0 ? [GwaiV8Position.action(key,row+3)] : [];
        row = GwaiV8Position.leaderScorchRow(effect);
        if(row > 0)
        {
            var units:Array = board[GwaiV8Position.slot(enemy,row)]; var total:Number = 0; var eligible:Boolean = false;
            for(i = 0; i < units.length; ++i)
            {
                total += power(units[i]);
                eligible = eligible || (GwaiV8Position.isType(cards[units[i]],8) && !GwaiV8Position.isType(cards[units[i]],128));
            }
            return eligible && total >= 10 ? [GwaiV8Position.action(key)] : [];
        }
        if(effect == 9) return board[GwaiV8Position.slot(-1,9)].length > 0 ? [GwaiV8Position.action(key)] : [];
        if(effect == 11 || effect == 12 || effect == 13)
        {
            options = weatherTemplates(effect == 11 ? 25 : effect == 12 ? 24 : 23,effect == 12 ? 25 : -1);
            return options.length == 1 ? [GwaiV8Position.action(key,9,options[0])] : [];
        }
        if(effect == 10)
        {
            options = weatherTemplates(); for(i = 0; i < options.length; ++i) out.push(GwaiV8Position.action(key,9,options[i]));
            return out;
        }
        if(effect == 15 || effect == 16)
        {
            options = recoveryTargets(effect == 15 ? side : enemy); var seen:Object = {};
            for(i = options.length-1; i >= 0; --i)
            {
                target = options[i]; var template:int = cards[target].template;
                if(!seen[template]) { seen[template] = true; out.push(GwaiV8Position.action(key,-1,target)); }
            }
            return out;
        }
        if(effect == 14) return [GwaiV8Position.action(key)];
        if(effect == 44) return recoveryTargets(0).length > 0 || recoveryTargets(1).length > 0 ? [GwaiV8Position.action(key)] : [];
        if(effect == 36)
            for(row = 4; row <= 5; ++row)
            {
                options = board[GwaiV8Position.slot(side,row)];
                for(i = 0; i < options.length; ++i)
                    if(agileUnit(options[i]) && repositionGain(options[i]) > 0) return [GwaiV8Position.action(key)];
            }
        return out;
    }
    public function actions():Array
    { return cardActions().concat(leaderActions()); }
    public function apply(move:Object):GwaiV8Position
    {
        if(move.source != leaders[player]) return applyCard(move);
        var effect:int = leaderEffect(player); var legal:Boolean = false;
        if((effect == 15 || effect == 16) && leaderModeled(player))
            legal = recoveryTargets(effect == 15 ? this.player : 1-this.player).indexOf(move.target) >= 0;
        else
        {
            var available:Array = leaderActions();
            for(var i:int = 0; i < available.length; ++i)
                if(available[i].source == move.source && available[i].slot == move.slot && available[i].target == move.target && move.chain.length == 0) legal = true;
        }
        if(!legal) throw new Error("illegal projected leader action");
        return applyLeader(move);
    }
    public function applyLeader(move:Object):GwaiV8Position
    {
        var state:GwaiV8Position = clone(); var side:int = player; var effect:int = leaderEffect(side);
        state.leader_ready[side] = false; var row:int = GwaiV8Position.leaderHornRow(effect); var card:Object; var key:int; var i:int;
        if(row > 0)
        {
            --state.next_key;
            card = {key:state.next_key,template:1,power:0,types:71,effects:[27],targets:[],owner:side,player:side,row:move.slot,applied:[],faction:0,banished_on_clear:false};
            state.cards[card.key] = card; state.placeModifier(card,move.slot,side);
        }
        else if(GwaiV8Position.leaderScorchRow(effect) > 0) state.scorch([1-side],[GwaiV8Position.leaderScorchRow(effect)]);
        else if(effect == 9)
        {
            var weather:Array = state.board[GwaiV8Position.slot(-1,9)].slice();
            for(i = 0; i < weather.length; ++i) state.removeFromBoard(weather[i]);
        }
        else if([10,11,12,13].indexOf(effect) >= 0)
        {
            --state.counts[move.target]; --state.next_key; card = GwaiV8Position.copyMap(state.catalog[move.target]);
            card.key = state.next_key; card.owner = side; card.player = side; card.row = 1;
            state.cards[card.key] = card; state.playWeather(card);
        }
        else if(effect == 15 || effect == 16)
        {
            var source:int = effect == 15 ? side : 1-side; card = GwaiV8Position.copyMap(state.cards[move.target]);
            state.grave[source] = GwaiV8Position.without(state.grave[source],card.key);
            card.player = side; card.row = 1; card.applied = []; state.cards[card.key] = card;
            state.hand = state.hand.concat([card.key]);
        }
        else if(effect == 44)
        {
            for(var s:int = 0; s < 2; ++s)
            {
                var moved:Array = state.recoveryTargets(s);
                for(i = 0; i < moved.length; ++i)
                {
                    key = moved[i]; state.grave[s] = GwaiV8Position.without(state.grave[s],key);
                    if(s == side) { var template:int = state.cards[key].template; state.counts[template] = int(state.counts[template])+1; }
                }
            }
        }
        else if(effect == 36)
        {
            var units:Array = state.board[GwaiV8Position.slot(side,4)].concat(state.board[GwaiV8Position.slot(side,5)]);
            for(i = 0; i < units.length; ++i)
            {
                key = units[i];
                if(!state.agileUnit(key) || state.repositionGain(key) <= 0) continue;
                card = state.cards[key];
                if(!GwaiV8Position.subset(card.effects,[0,32,35])) throw new GwaiV8Unsupported("repositioned unit would re-trigger an effect");
                row = card.row == 5 ? 4 : 5; state.removeFromBoard(key,false); state.placeUnit(key,row,side);
            }
        }
        return state;
    }
    public function applyCard(move:Object):GwaiV8Position
    {
        var legal:Boolean = false; var available:Array = cardActions();
        for(var i:int = 0; i < available.length; ++i)
            if(available[i].source == move.source && available[i].slot == move.slot && available[i].target == move.target) legal = true;
        if(!legal) throw new Error("illegal projected card action");
        var state:GwaiV8Position = clone(); var card:Object = state.cards[move.source];
        state.hand = GwaiV8Position.without(state.hand,card.key);
        if(GwaiV8Position.has(card,GwaiV8Const.CardEffect_UnsummonDummy))
        {
            var target:Object = state.cards[move.target]; state.removeFromBoard(target.key,false);
            var recovered:Object = GwaiV8Position.copyMap(target); recovered.player = state.player; recovered.row = 1; recovered.applied = [];
            state.cards[target.key] = recovered; state.hand = state.hand.concat([target.key]);
            var dummy:Object = GwaiV8Position.copyMap(card); dummy.player = state.player; dummy.row = target.row; dummy.applied = [];
            state.cards[card.key] = dummy; state.board[GwaiV8Position.slot(state.player,target.row)] = state.board[GwaiV8Position.slot(state.player,target.row)].concat([card.key]);
        }
        else if(GwaiV8Position.isType(card,8)) state.placeUnit(card.key,move.slot,GwaiV8Position.isType(card,256) ? 1-state.player : state.player,move.chain);
        else if(GwaiV8Position.isType(card,64)) state.placeModifier(card,move.slot,state.player);
        else if(GwaiV8Position.isType(card,16)) state.playWeather(card);
        else if(GwaiV8Position.has(card,GwaiV8Const.CardEffect_Scorch))
        {
            state.scorch(); var spent:Object = GwaiV8Position.copyMap(card); spent.row = 2; spent.applied = []; state.cards[card.key] = spent;
            state.grave[card.owner] = state.grave[card.owner].concat([card.key]);
        }
        return state;
    }
}
internal class GwaiV8Unsupported extends Error
{
    public function GwaiV8Unsupported(message:String) { super(message); }
}
