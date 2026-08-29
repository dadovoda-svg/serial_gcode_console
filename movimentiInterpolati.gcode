; inviare manualmente M999 e G28
;G28

;preparazione movimenti
M700 v=100 a=240
M702 s=0

;ribadisco "home"
G12 x=247 y=0 z=257.892 rz=0 ry=0 rx=0
M400

G12 X=320 Y=-80 Z=50 Rz=0 Ry=0 Rx=0
M400

M702 s=1 L=10 R=2
G12 X=320 Y=80 Z=50 Rz=0 Ry=0 Rx=0
M400
G12 X=320 Y=80 Z=150 Rz=0 Ry=0 Rx=0
M400
G12 X=320 Y=-80 Z=150 Rz=0 Ry=0 Rx=0
M400
G12 X=320 Y=-80 Z=50 Rz=0 Ry=0 Rx=0
M400

M702 s=0
G12 x=247 y=0 z=257.892 rz=0 ry=0 rx=0
M400

;G30










