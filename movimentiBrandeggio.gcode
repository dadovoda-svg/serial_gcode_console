; inviare manualmente M999 e G28
;G28

;preparazione movimenti
M700 v=10 a=90
M702 s=0

;ribadisco "home"
G12 x=247 y=0 z=257.892 rz=0 ry=0 rx=0

g2 j3=-90 j2=0 j5=0
m400 1000
g2 j3=-90 j2=89 j5=0
m400 1000

M700 v=3 a=30
g2 j1=-20
m400 1000
g2 j1=-20
m400 1000
g2 j1=0 

;G30













