#minicom -b 115200 -D /dev/ttyACM0


g M114
g M115
g G28

g M700 v=30 a=120
g M702 s=1 L=15 R=5
# home
g M700 v=30 a=120
g M702 s=1 L=15 R=5
# home
g G10 x=247 y=0 z=257.892 rz=0 ry=0 rx=0

#posa iniziale
g G10 x=300 y=0 z=180 rz=0 ry=0 rx=0
g G12 x=300 y=0 z=180 rz=0 ry=0 rx=0

#interpolazione

g M702 s=0

#relatvi
g G15 y=-150
g G15 ry=-90
g G15 y=20
g G15 X=20

g G15 ry=-45
g G15 z=-50 y=-100
g G15 z=100 y=200
g G15 z=-100 y=-200

g M700 v=30 a=120
g M702 s=1 L=15 R=5
g g15 x=20 y=-100 z=-150 ry=-45
g g15 y=200
g G10 x=247 y=0 z=257.892 rz=0 ry=0 rx=0


segnalazione 1072569146 per il numero 0264139199
