"""Where the robot's body parts are, so outfits can line up with them.

Origin is the ground point between his feet; y grows downward, so
everything is at negative y. Units are design pixels.
"""
HEAD_TOP = -112          # top edge of the head
HEAD_HALF_W = 37
SCREEN_TOP = -104        # face screen
EYE_Y, EYE_X = -87, 12   # eye centres at (±EYE_X, EYE_Y)
MOUTH_Y = -75
BODY_TOP, BODY_BOTTOM = -53, -18
BODY_HALF_W = 22
SHOULDER_X, SHOULDER_Y = 21, -45   # arm pivots at (±SHOULDER_X, SHOULDER_Y)
ARM_LENGTH = 19                    # pivot to hand centre
ANTENNA_TOP = -132       # top of the antenna ball with no hat on
