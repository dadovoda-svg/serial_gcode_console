; inviare manualmente M999 e G28
;G28

;preparazione movimenti
M700 v=100 a=240
M702 s=0

;ribadisco "home"
G12 x=247 y=0 z=257.892 rz=0 ry=0 rx=0

;movimento assoluto (con singolarità)
G15 x=20 y=-100 z=-150 ry=-50
;movimento assoluto (senza singolarità)
;G15 x=20 y=-100 z=-150 ry=-40

M400

M702 s=1 L=10 R=2
G15 y=200
M400
M702 s=0

G12 x=247 y=0 z=257.892 rz=0 ry=0 rx=0
M400

M702 s=1 L=10 R=2
G15 rx=25 ry=-30
M400
G23
g22 x=100
m400
G22 y=100
m400
G22 x=-100
m400
G22 y=-100
m400
M702 s=0

G12 x=247 y=0 z=257.892 rz=0 ry=0 rx=0

G1 J3=30
M400
G1 J3=-45
M400

G1 J1=45
M400
G1 J1=-45
M400

G12 x=247 y=0 z=257.892 rz=0 ry=0 rx=0
M400

G12 X=250 Y=20.000 Z=3 Rz=0.000 Ry=-0.000 Rx=-0.000
M400

M702 s=1 L=10 R=2
G12 X=250 Y=-20.000 Z=3 Rz=0.000 Ry=-0.000 Rx=-0.000
M400
G12 X=210 Y=-20.000 Z=3 Rz=0.000 Ry=-0.000 Rx=-0.000
M400
G12 X=210 Y=20.000 Z=3 Rz=0.000 Ry=-0.000 Rx=-0.000
M400
G12 X=250 Y=20.000 Z=3 Rz=0.000 Ry=-0.000 Rx=-0.000
M400
M702 s=0

G12 x=247 y=0 z=257.892 rz=0 ry=0 rx=0
M400

;M30











