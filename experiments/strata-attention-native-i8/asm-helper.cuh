// Experimental exact INT8 -> FP16 fragment conversion for gfx11 prompt attention.
// Shared with the exhaustive GPU test; never selected by default.
#pragma once
#include <hip/hip_runtime.h>
#include <cstdint>

namespace strata::kernels::hip_detail {
using I8Half16 = _Float16 __attribute__((ext_vector_type(16)));

__device__ __forceinline__ I8Half16 native_i8_to_half16(const uint32_t* words) {
    I8Half16 result;
#pragma unroll
    for (int i = 0; i < 16; ++i) {
        const int value = (int) (int8_t) (words[i / 4] >> (8 * (i % 4)));
#if defined(__gfx1100__) || defined(__gfx1101__) || defined(__gfx1102__) || defined(__gfx1103__) || \
    defined(__gfx1150__) || defined(__gfx1151__)
        uint32_t bits;
        // The instruction reads the signed low 16 bits; INT8 is exactly
        // representable in FP16. Only the low 16 output bits are consumed.
        asm("v_cvt_f16_i16_e64 %0.l, %1.l" : "=v"(bits) : "v"(value));
        result[i] = __builtin_bit_cast(_Float16, (uint16_t) bits);
#else
        result[i] = (_Float16) value;
#endif
    }
    return result;
}
}  // namespace strata::kernels::hip_detail
