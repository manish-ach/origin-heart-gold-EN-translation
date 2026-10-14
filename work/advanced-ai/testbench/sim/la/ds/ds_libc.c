/* word copies when both ends are aligned, as MI_CpuCopy32 / MI_CpuFill32 would do on the DS */
#include <string.h>
#include <stdint.h>

void *memcpy(void *d, const void *s, size_t n)
{
    unsigned char *dp = d;
    const unsigned char *sp = s;
    if ((((uintptr_t)dp | (uintptr_t)sp) & 3) == 0) {
        uint32_t *dw = (uint32_t *)dp;
        const uint32_t *sw = (const uint32_t *)sp;
        for (; n >= 16; n -= 16, dw += 4, sw += 4) {
            uint32_t a = sw[0], b = sw[1], c = sw[2], e = sw[3];
            dw[0] = a, dw[1] = b, dw[2] = c, dw[3] = e;
        }
        for (; n >= 4; n -= 4)
            *dw++ = *sw++;
        dp = (unsigned char *)dw, sp = (const unsigned char *)sw;
    }
    while (n--)
        *dp++ = *sp++;
    return d;
}

void *memset(void *d, int c, size_t n)
{
    unsigned char *dp = d;
    if (((uintptr_t)dp & 3) == 0) {
        uint32_t v = (unsigned char)c * 0x01010101u, *dw = (uint32_t *)dp;
        for (; n >= 16; n -= 16, dw += 4)
            dw[0] = v, dw[1] = v, dw[2] = v, dw[3] = v;
        for (; n >= 4; n -= 4)
            *dw++ = v;
        dp = (unsigned char *)dw;
    }
    while (n--)
        *dp++ = (unsigned char)c;
    return d;
}

int memcmp(const void *a, const void *b, size_t n)
{
    const unsigned char *x = a, *y = b;
    for (; n; n--, x++, y++)
        if (*x != *y)
            return *x - *y;
    return 0;
}
