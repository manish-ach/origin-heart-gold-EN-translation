/* The advanced AI's tuning table (TUNING_DESIGN.md section 2): its judgment constants, one copy per side, which
   tools/aivsai.py and tools/aitune.py overwrite for self-play matches. The real game reads the compiled defaults.
   X(name, default, lo, hi, step): tools/aitune.py parses these lines. MY_ROLL's range stays below THEIR_ROLL's
   (best_rate and prime tell the sides apart by roll == MY_ROLL). Every value is a u16 */
#define TUNE_VERSION 2
#define TUNE_LIST(X) \
    X(TEMPO,          78,  40,  200,  40) \
    X(WORTH_BASE,     231, 100,  450, 100) \
    X(WORTH_STRONG,   651, 400,  950, 150) \
    X(MY_ROLL,        900, 850,  924,  20) \
    X(THEIR_ROLL,     953, 926, 1000,  20) \
    X(SWITCH_COST,     66,  10,  150,  24) \
    X(KO_TEMPO,       100,   0,  300,  48) \
    X(DAMAGE_CREDIT,   98,   0,  200,  36) \
    X(ROLE_W,        1003,   0, 2000, 400) \
    X(LAST_BONUS,     478, 200, 1500, 200)
