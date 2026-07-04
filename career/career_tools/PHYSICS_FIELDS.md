# TSU physics fields — reference

Status: **field mapping verified in-game** (2026-07-03) by loading a generated
vehicle ("Claude GT3 Test") and comparing every editor slider against the
bytes written — all sections matched.

Defaults = serialization defaults (used when a field is omitted from the
file / spec). The in-game "new vehicle" preset differs from these — the editor
starts new cars at e.g. mass 1600, maxSpeed 200, bounciness 0.25.

Min/Max from the game's metadata constants are enforced by
`tsu_veh.validate()` at build time; fields marked ? have no known constant
(the editor slider may still clamp).

## physics.weight
| field   | default | min | max   |
|---------|---------|-----|-------|
| mass    | 1000    | 1   | 10000 |
| massY   | 0       | ?   | ?     |
| massZ   | 0       | ?   | ?     |
| gravity | 20      | 0   | 100   |

## physics.speed
| field             | default | min   | max  | notes |
|-------------------|---------|-------|------|-------|
| maxSpeed          | 180     | 1     | 1000 | |
| viscosity         | 0.75    | 0.001 | 10   | |
| acceleration      | 1.0     | 0.1   | 10   | |
| reverseMultiplier | 0.33    | 0.01  | 4    | |
| engineFriction    | 0       | ?     | ?    | deprecated, hidden in editor |
| flyingViscosity   | 0.3     | 0.001 | ?    | |

## physics.braking  (editor-verified order)
| field                 | default | min | max  |
|-----------------------|---------|-----|------|
| braking               | 20      | 0   | 1000 |
| parkBraking           | 20      | ?   | ?    |
| parkSpeed             | 2       | ?   | ?    |
| lockingStartTime      | 0.5     | ?   | ?    |
| complexLocking        | false   |     |      |
| lockedBrakeMultiplier | 1       | ?   | ?    |
| cooldownMultiplier    | 2       | 0   | 255  |
| lockedGripMultiplier  | 1       | ?   | ?    |

## physics.steering  (editor-verified)
| field             | default | min | max  | notes |
|-------------------|---------|-----|------|-------|
| grip              | 20      | 0   | 1000 | |
| maxSteering       | 150     | ?   | ?    | |
| changeSpeed       | 2000    | ?   | ?    | |
| changeReturnSpeed | 2000    | ?   | ?    | |
| steer4            | ?       | ?   | ?    | hidden in editor (deprecated) |
| flyingSteering    | 50      | ?   | ?    | |
| flyingChangeMult  | 0.2     | ?   | ?    | |
| neutralReturn     | 1       | ?   | ?    | |
| steering2.fullSteeringSpeed | 10 | ? | ?  | |
| steering2.s1..s7  | ?       |     |      | unknown; probably incl. Reverse Steering enum |

## physics.oversteering  (editor-verified; GT3s use small values like 0.43)
all four: default `always`=30 others 0, min -1000, max 1000

## physics.sliding  (editor-verified)
| field             | default | min | max  | notes |
|-------------------|---------|-----|------|-------|
| slidingAngle      | 22.5    | ?   | ?    | |
| gradualRange      | 0       | ?   | ?    | |
| gradualGrip       | true    |     |      | |
| slideBraking      | 10      | 0   | 1000 | |
| slideDeceleration | 0       | ?   | ?    | deprecated, hidden in editor |
| slideAcceleration | 1       | ?   | ?    | |
| minSmokeAngle     | 10      | 0   | 255  | |
| minSmokeRange     | 10      | 0   | 255  | |

## physics.spring  (editor-verified)
maxLength 0.3 (max 1.0) · maxAcceleration 1 · damping 0.2 ·
backLength 1 (max 5) · backAcceleration 1 · backDamping 1

## physics.downforce  (editor-verified; the two bools live in the mask byte)
downforce 0 · springAffectsGrip false · springAffectsBraking false ·
maxSpringGs 0.5 · maxAccSpringGs 0

## physics.weightTransfer  (editor-verified)
turning 0 · braking 0 · accelerating 0 · viscosityReduction 0.5

## physics.contact  (editor-verified)
bounciness 0.75 · staticFriction 0.6 · dynamicFriction 0.6 ·
bounceCombine / frictionCombine: enum int 0=Average 1=Multiply 2=Minimum 3=Maximum

## mid sections (audio etc., editor-verified)
- engine: engineSound (u8 sample index; 35="V8 German", ~33="V8 Italian 1"),
  pitch 1, channels, lowMax 0.3, medMaxRel 0.5, highMax 0.8, medExtra 0.2
- engine2: gasSpeed 5, onlyGasOn false, gasOffPitch 0.9, gasOffVolume 0.75,
  pitchSpeed 2, flyingPitch 0.25
- gearAudio: gearAudio true, shiftUp 0.9, shiftDown 0.8, shiftDownIdle 0.6
- gearRatios: ratio1..8 (defaults 2.5 / 1.6 / 1.25 / 0.975 / 0…)
- damage: maxHitPoints 10000 (min 500, max 50000)

## header
- Tags (Style / Speed / Acceleration / Turning / Sliding dropdowns) are the
  bitmask-encoded bytes in the header (bits 0-4; bit 5 = creation game
  version). Claude GT3 Test inherited Style=Realistic, Sliding=Anti Slider
  from the Mercedes template (bit0=0, bit4=0).
- Model dropdown = the u32 after description: 6=Countach-style, 8=formula,
  10=Mustang-style, 12="Super 3", 13=Ferrari-296-style.

## still unknown
- steering.steer4, steering2.s1..s7 (incl. where Reverse Steering enum lives)
- engine.channels serialization (dropdown "All"; never observed non-default)
- "special" trailing mid-section (probably Camber Angle Front/Rear — never
  observed non-default) and the sec1/sec3 sections (probably Physics Model /
  collision shape related)
- physics.gears (gearCount) and the 5 trailing physics bytes
