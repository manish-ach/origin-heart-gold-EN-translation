// Field and side state, adapted from @smogon/calc field.ts (MIT; see LICENSE).
// Removed: G-Max side effects (Steelsurge, Vine Lash, Wildfire, Cannonade, Volcalith), Nightmare, Salt Cure.
import type {FieldState, GameType, SideState, Terrain, Weather} from './types.ts';

export class Side {
  spikes: number;
  isSR: boolean;
  isReflect: boolean;
  isLightScreen: boolean;
  isProtected: boolean;
  isSeeded: boolean;
  isForesight: boolean;
  isCharge: boolean;
  isTailwind: boolean;
  isHelpingHand: boolean;
  isFlowerGift: boolean;
  isPowerTrick: boolean;
  isFriendGuard: boolean;
  isAuroraVeil: boolean;
  isBattery: boolean;
  isPowerSpot: boolean;
  isSteelySpirit: boolean;
  isSwitching?: 'out' | 'in';
  isGlaiveRushed: boolean;

  constructor(side: SideState = {}) {
    this.spikes = side.spikes || 0;
    this.isSR = !!side.isSR;
    this.isReflect = !!side.isReflect;
    this.isLightScreen = !!side.isLightScreen;
    this.isProtected = !!side.isProtected;
    this.isSeeded = !!side.isSeeded;
    this.isForesight = !!side.isForesight;
    this.isCharge = !!side.isCharge;
    this.isTailwind = !!side.isTailwind;
    this.isHelpingHand = !!side.isHelpingHand;
    this.isFlowerGift = !!side.isFlowerGift;
    this.isPowerTrick = !!side.isPowerTrick;
    this.isFriendGuard = !!side.isFriendGuard;
    this.isAuroraVeil = !!side.isAuroraVeil;
    this.isBattery = !!side.isBattery;
    this.isPowerSpot = !!side.isPowerSpot;
    this.isSteelySpirit = !!side.isSteelySpirit;
    this.isSwitching = side.isSwitching;
    this.isGlaiveRushed = !!side.isGlaiveRushed;
  }

  clone() {
    return new Side(this);
  }
}

export class Field {
  gameType: GameType;
  weather?: Weather;
  terrain?: Terrain;
  isMagicRoom: boolean;
  isWonderRoom: boolean;
  isGravity: boolean;
  isAuraBreak: boolean;
  isFairyAura: boolean;
  isDarkAura: boolean;
  isBeadsOfRuin: boolean;
  isSwordOfRuin: boolean;
  isTabletsOfRuin: boolean;
  isVesselOfRuin: boolean;
  isSpreadSingle: boolean;
  attackerSide: Side;
  defenderSide: Side;

  constructor(field: FieldState = {}) {
    this.gameType = field.gameType || 'Singles';
    this.terrain = field.terrain;
    this.weather = field.weather;
    this.isMagicRoom = !!field.isMagicRoom;
    this.isWonderRoom = !!field.isWonderRoom;
    this.isGravity = !!field.isGravity;
    this.isAuraBreak = !!field.isAuraBreak;
    this.isFairyAura = !!field.isFairyAura;
    this.isDarkAura = !!field.isDarkAura;
    this.isBeadsOfRuin = !!field.isBeadsOfRuin;
    this.isSwordOfRuin = !!field.isSwordOfRuin;
    this.isTabletsOfRuin = !!field.isTabletsOfRuin;
    this.isVesselOfRuin = !!field.isVesselOfRuin;
    this.isSpreadSingle = !!field.isSpreadSingle;
    this.attackerSide = new Side(field.attackerSide || {});
    this.defenderSide = new Side(field.defenderSide || {});
  }

  hasWeather(...weathers: Weather[]) {
    return !!(this.weather && weathers.includes(this.weather));
  }

  hasTerrain(...terrains: Terrain[]) {
    return !!(this.terrain && terrains.includes(this.terrain));
  }

  swap() {
    [this.attackerSide, this.defenderSide] = [this.defenderSide, this.attackerSide];
    return this;
  }

  clone() {
    return new Field({
      gameType: this.gameType,
      weather: this.weather,
      terrain: this.terrain,
      isMagicRoom: this.isMagicRoom,
      isWonderRoom: this.isWonderRoom,
      isGravity: this.isGravity,
      isAuraBreak: this.isAuraBreak,
      isDarkAura: this.isDarkAura,
      isFairyAura: this.isFairyAura,
      isBeadsOfRuin: this.isBeadsOfRuin,
      isSwordOfRuin: this.isSwordOfRuin,
      isTabletsOfRuin: this.isTabletsOfRuin,
      isVesselOfRuin: this.isVesselOfRuin,
      isSpreadSingle: this.isSpreadSingle,
      attackerSide: this.attackerSide,
      defenderSide: this.defenderSide,
    });
  }
}
