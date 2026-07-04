# TSU vehicle editor — official parameter descriptions & dropdown values

Tooltips extracted verbatim from the game's IL2CPP metadata (attribute blob),
i.e. the exact texts shown when hovering parameters in the in-game editor.

## CarPhysicsProperties
- **weight** — Mass and weight related properties.
- **contact** — Properties related to car body making contact with other objects.
- **speed** — Speed and acceleration related properties.
- **braking** — Braking properties.
- **steering** — Steering properties.
- **oversteering** — Oversteering properties, modify to control when car starts sliding.
- **sliding** — Sliding properties.
- **spring** — Spring related properties.
- **downforce** — Properties defining how downforce and spring state affect properties like braking and grip.
- **weightTransfer** — Properties defining how much there is weight transfer (torque for physical body).

## WeightProperties
- **mass** — Mass of the vehicle [kg]. This affects collisions only. E.g. acceleration, gravity and springs are not affected by mass.
- **massY** — How much above wheels the center of mass is [m]. The smaller the value is the harder it is to tip over.
- **massZ** — How much towards front (or back) the center of mass is [m].
- **gravity** — Gravity [m/s^2]. 10 is "realistic" but 20 suits better arcadeish top-down racing.

## ContactProperties
- **bounciness** — Bounciness in collisions.
- **staticFriction** — Static friction.
- **dynamicFriction** — Dynamic friction.
- **bounceCombine** — The preferred method of combining bounciness between two materials. Precedence in case two objects have a different combine function: Maximum, Multiply, Minimum, Average.
- **frictionCombine** — The preferred method of combining friction between two materials. Precedence in case two objects have a different combine function: Maximum, Multiply, Minimum, Average.

## SpeedProperties
- **maxSpeed** — Maximum speed in km/h on default tarmac.
- **viscosity** — Viscosity, causes slow-down based on speed (deceleration = speed * viscosity). Base acceleration = max speed x viscosity, so increasing viscosity also increases acceleration.
- **acceleration** — Initial acceleration multiplier. Like viscosity, affects how quickly to get to the max speed, but without the slowdown effect of viscosity. 1 for uniform acceleration at every speed, limited only by viscosity.
- **reverseMultiplier** — Multiplier for reverse acceleration.
- **flyingViscosity** — Viscosity when flying.

## BrakingProperties
- **braking** — Braking deceleration [m/s^2].
- **parkBraking** — How much braking deceleration there is when not accelerating or braking at slow speed. [m/s^2] Without this, car will start slowly moving downhill when not doing anything.
- **parkSpeed** — Speed at which parking force starts taking effect.
- **complexLocking** — Whether the more complex brake locking logic is activated. Enable to control when brakes are locked (smoke coming) and how it affects physics.
- **lockingStartTime** — How long to do max braking before brakes are locked and smoke starts coming out.
- **cooldownMultiplier** — How much quicker the brake cooldown happens compared to getting locked. With high values, even a small non-braking time resets the locking timer. With 1, resetting the timer takes as long as the time to cause locking.
- **lockedBrakeMultiplier** — When the brakes are locked, braking deceleration is multiplied by this.
- **lockedGripMultiplier** — When the brakes are locked, the grip is multiplied by this.

## SteeringProperties
- **grip** — Grip, rotation in rad/s is grip / speed. Defines how quickly the car can turn without starting to slide. If there is no oversteering, this also caps the maximum turning speed.
- **maxSteering** — Maximum steering speed in deg/s. This only has an effect if grip and/or oversteering values are so high that the full steering speed would be more than this.
- **changeSpeed** — Steering change speed in deg/s^2. If this is low, turning becomes more sluggish.
- **changeReturnSpeed** — Steering change return to 0 speed in deg/s^2. Also affects recovering from spins.
- **neutralReturn** — Multiplier to change return speed when not countersteering but keeping steering on neutral. By using smaller values steering returns to neutral smoother unless steering to opposite direction.
- **limitingMode** — DISABLED - keeping as a reference but not used at the moment - How the vehicle behaves when steering is limited.
- **flyingSteering** — Flying steering in deg/s^2.
- **flyingChangeMult** — Flying steering change multiplier. Set to 0 to not be able to change steering when flying.
- **fullSteeringSpeed** — Car speed required for full steering. If 0, car can turn even when not moving.
- **reverseSteering** — Reverse steering mode - in realistic mode, steering rotation is inverted when reversing. Hovercraft mode might work better with extreme sliding or with zero fullSteeringSpeed.

## OversteeringProperties
- **always** — Oversteering in deg/s. Positive values causes oversteering and sliding.
- **sliding** — Extra oversteering in deg/s when sliding.
- **braking** — Extra oversteering in deg/s when braking.
- **accelerating** — Extra oversteering in deg/s when accelerating.

## SlidingProperties
- **slidingAngle** — When slip angle (angle difference of velocity and forward) is more than this (in degrees), car is sliding.
- **gradualRange** — If non-zero, sliding effects gradually increase based on the extent to which the slip angle exceeds the sliding angle. Full effect at sliding angle + gradual range.
- **gradualGrip** — If true, grip starts getting worse before sliding starts (multiplied by cos(slipAngle)). If false, grip stays the same until sliding starts.
- **slideBraking** — Braking deceleration when sliding [m/s^2].
- **deprecatedSlideDeceleration** — DEPRECATED: Acceleration is reduced by this amount when sliding [m/s^2].
- **slideAcceleration** — Acceleration is multiplied by this value when sliding.
- **minSmokeAngle** — If non-zero, smoke and skidmark only appear if slip angle is at least this much when sliding (in degrees). This only affects the visual smoke effect, not the actual physics. Usually, you want to keep this at 0 so that the effect is directly tied to sliding.
- **minSmokeRange** — If Min Smoke Angle is non-zero, this defines how long the gradual range for full smoke effect is (in degrees). This doesn't do anything if Min Smoke Angle is 0.

## SpringProperties
- **maxLength** — Spring max length.
- **maxAcceleration** — How much one spring causes acceleration to car when fully compressed. Relative to the default gravity so that 1 means one wheel supports the whole car alone in default gravity (20).
- **damping** — Spring damping defined as acceleration per compression speed. Relative to the default gravity.
- **backLength** — Back wheel max length is multiplied by this value (but not going over max). 1 for the same as in front.
- **backAcceleration** — Back wheel max acceleration is multiplied by this value. 1 for the same as in front.
- **backDamping** — Back wheel spring damping acceleration is multiplied by this value. 1 for the same as in front.

## DownforceProperties
- **downforce** — Force downwards from speed. Grip and braking are increased by downforce * (speed / maxSpeed)^2 * cos(slipAngle)
- **springAffectsGrip** — Determines whether grip is affected by compression state of front wheel springs. If true, downforce effect follows indirectly from spring state.
- **springAffectsBraking** — Determines whether braking force is affected by compression state of wheel springs. If true, downforce effect follows indirectly from spring state
- **maxSpringGs** — How many Gs over downforce can springs cause grip and braking force (when springs affect). High values might be realistic but also sometimes cause super-quick turning.
- **maxAccSpringGs** — If non-zero, acceleration is reduced until back wheel weight is enough (1 neutral position).

## WeightTransferProperties
- **turning** — Torque when turning with grip.
- **braking** — Torque when braking.
- **accelerating** — Torque when accelerating.
- **viscosityReduction** — Amount of viscosity reduced from acceleration torque. 1 means viscosity is fully removed and no torque at max speed, 0 means reduction only comes from engine friction.

## VehicleDamageProperties
- **maxHitPoints** — Max health / hit points. This only matters on events where damage is active.

## VehicleSpecialProperties
- **camberAngleFront** — Camber angle for the front wheels, that is the leaning/tilting of the front wheels. Use non-zero for special wheel looks. Doesn't affect physics.
- **camberAngleRear** — Camber angle for the rear wheels, that is the leaning/tilting of the rear wheels. Use non-zero for special wheel looks. Doesn't affect physics.

## VehicleAudioProperties
- **engine** — Engine sound specific settings
- **gears** — Gear sound specific settings

## VehicleEngineAudioProperties
- **pitch** — Pitch multiplier
- **channels** — Determines whether all or just one sound channel is used for the engine sound
- **lowMax** — Relative RPM for the max volume of low channel (in All mode)
- **medMaxRel** — Medium channel max volume position in relation to low and high channels (in All mode)
- **highMax** — Relative RPM for the max volume of high channel (in All mode)
- **medExtra** — How much over high max medium channel goes (in All mode) - If 0, medium channel is completely out at high max
- **gasSpeed** — How quickly engine gas state audio changes after control changes
- **onlyGasOn** — Whether the same sample is used when gas is on and off
- **gasOffPitch** — How much pitch is modified when gas is off in OnlyGasOn mode
- **gasOffVolume** — How much volume is modified when gas is off in OnlyGasOn mode
- **flyingPitch** — How much pitch is increased when using gas in the air

## VehicleGearAudioProperties
- **gearAudio** — Whether engine audio pitch simulates using gears. This does not affect physics.
- **shiftUp** — Relative RPM when shifting up gear
- **shiftDown** — Relative RPM of the gear below to shift to it when gas is on
- **shiftDownIdle** — Relative RPM of the gear below to shift to it when gas is not on
- **ratio2** — Gear 2 ratio, 0 for none
- **ratio3** — Gear 3 ratio, 0 for none
- **ratio4** — Gear 4 ratio, 0 for none
- **ratio5** — Gear 5 ratio, 0 for none
- **ratio6** — Gear 6 ratio, 0 for none
- **ratio7** — Gear 7 ratio, 0 for none
- **ratio8** — Gear 8 ratio, 0 for none

## VehicleProperties
- **makerId** — User id of the maker
- **name** — Name of the vehicle
- **description** — Free-form description of the vehicle
- **tags** — Tags for the vehicle. Change if there is something special. Tags can be used in searching for specific kinds of vehicles.
- **collisionShape** — Collision shape
- **damage** — Damage and hit point properties
- **audio** — Audio properties
- **special** — Special effect and appearance properties
- **physicsProperties** — Physics properties related to the model

## Dropdown enums (from metadata)

- **Model** (`modelId`, VehicleModelType): 0=Sport1, 1=Sport2, 2=Civilian1, 3=Sedan1, 4=Drifter, 5=Super1, 6=Super2, 7=HeavyFormula, 8=Formula, 9=Muscle1, 10=Muscle2, 11=Muscle3, 12=Super3, 13=Super4, 14=Super5, 15=Sport3
- **Engine** (`engineSound`, EngineSoundType): 0=None, 1=I4_German_1, 2=I4_German_2, 3=I4_German_3, 4=I4_Japanese, 5=I4_Japanese_VTEC, 6=I4_Serbian, 7=Diesel_German, 8=I6_German_1, 9=I6_German_2, 10=I6_German_M_1, 11=I6_German_M_2, 12=I6_German_M_3, 13=I6_Japanese_1, 14=I6_Japanese_2, 15=Boxer_German, 16=Boxer_Japanese_1, 17=Boxer_Japanese_2, 18=Rotary_X3, 19=Rotary_X7, 20=Rotary_X8F, 21=Rotary_X8_1, 22=Rotary_X8_2, 23=Rotary_X8_3, 24=Rotary_4_Rotor, 25=V6_Japanese_1, 26=V6_Japanese_2, 27=V8_American_Classic_1, 28=V8_American_Classic_2, 29=V8_American_Modern_1, 30=V8_American_Modern_2, 31=V8_Italian_1 (default), 32=V8_Italian_2, 33=V8_Formula_1, 34=V8_Italian_F355, 35=V8_German, 36=V8_German_M_1, 37=V8_German_M_2, 38=V8_German_M_3, 39=V10_German, 40=V10_Italian, 41=V12_British, 42=V12_Italian
- **Channels** (EngineChannelMode): 0=All, 1=OnlyIdle, 2=OnlyLow, 3=OnlyMedium, 4=OnlyHigh
- **Reverse Steering** (ReverseSteeringType): 0=Realistic, 1=Hovercraft
- **Bounce/Friction Combine** (PhysicMaterialCombine): 0=Average, 1=Multiply, 2=Minimum, 3=Maximum
- **Physics Model** (PhysicsModel): 0=DefaultCar

### Tags (header bitmask bytes, bits 0-4; unset bit = default value 1)
- **Style** (VehicleStyle): 0=Realistic, 1=Common (default), 2=Special, 3=Crazy
- **Speed** (VehicleSpeed): 0=LowSpeed, 1=MediumSpeed (default), 2=HighSpeed
- **Acceleration** (VehicleAcceleration): 0=LowAccel, 1=MediumAccel (default), 2=HighAccel
- **Turning** (VehicleTurning): 0=QuickTurning, 1=MediumTurning (default), 2=SlowTurning
- **Sliding** (VehicleSliding): 0=AntiSlider, 1=EasySlider (default), 2=Slider
