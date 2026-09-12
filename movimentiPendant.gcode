; inviare manualmente M999 e G28
;G28

;preparazione movimenti
M700 v=100 a=240
M702 s=0

;ribadisco "home"
G12 x=247 y=0 z=257.892 rz=0 ry=0 rx=0
M400

;simulazione domandi da pendandt cadenzati (movimento encoder)
M702 s=1 L=10 R=2

G14 z=-3
M401 200
G14 z=-1
M401 200
G14 z=-4
M401 200
G14 z=-8
M401 200
G14 z=-2
M401 200
G14 z=-3
M401 200
G14 z=-2
M401 200
G14 z=-4
M401 200
G14 z=-5
M401 200
G14 z=-1
M401 200
G14 z=-1
M401 200
G14 z=-2
M401 200
G14 z=-3
M401 200
G14 z=-3
M401 200
G14 z=-3
M401 200
G14 z=-3
M401 200
G14 z=-3
M401 200
G14 z=-3
M401 200
G14 z=-3
M401 200
G14 z=-3
M401 200
G14 z=-3
M401 200
G14 z=-3
M401 200
G14 z=-3
M401 200
G14 z=-3
M401 200
G14 z=-3
M401 200

M702 s=0

G12 x=247 y=0 z=257.892 rz=0 ry=0 rx=0
M400

;G30











