// Independent tile-shape probes. Include after the pinned upstream header.
// Preserve each output's ascending sequence of 16-wide WMMA operations.
namespace pfg {
template<bool Wide>
__global__ void __launch_bounds__(Wide ? 512 : 256) kernel_tile(
    const _Float16* __restrict__ X, const _Float16* __restrict__ W,
    float* __restrict__ Y, int M,int N,int K,int ldy,int accumulate,int ldx,int ldw) {
    constexpr int BN=Wide?512:128, WN=Wide?64:32, KT=Wide?32:64;
    constexpr int LD=KT+8, TN=WN/16, STEP=Wide?128:32;
    __shared__ __align__(16) _Float16 sA[128][LD];
    __shared__ __align__(16) _Float16 sB[BN][LD];
    const int tid=threadIdx.x,lane=tid&31,wave=tid>>5,l16=lane&15,hi=lane>>4;
    const int wm=wave&1,wn=wave>>1;
    const int num_m=(M+127)/128,num_n=(N+BN-1)/BN,b=blockIdx.x;
    const int group=b/(8*num_n),first_m=group*8,gsize=min(8,num_m-first_m);
    const int m0=(first_m+(b%(8*num_n))%gsize)*128,n0=((b%(8*num_n))/gsize)*BN;
    const int sr=Wide?(tid>>2):(tid>>3),sq=Wide?(tid&3):(tid&7);
    auto ldA=[&](int k0,int r)->uint4 {
        return *reinterpret_cast<const uint4*>(X+(size_t)min(m0+r,M-1)*ldx+k0+8*sq);
    };
    auto ldB=[&](int k0,int r)->uint4 {
        return *reinterpret_cast<const uint4*>(W+(size_t)min(n0+r,N-1)*ldw+k0+8*sq);
    };
    uint4 ra0,ra1,ra2,ra3,rb0,rb1,rb2,rb3;
    auto load=[&](int k0) {
        ra0=ldA(k0,sr);
        if constexpr(!Wide){ra1=ldA(k0,sr+32);ra2=ldA(k0,sr+64);ra3=ldA(k0,sr+96);}
        rb0=ldB(k0,sr);rb1=ldB(k0,sr+STEP);rb2=ldB(k0,sr+2*STEP);rb3=ldB(k0,sr+3*STEP);
    };
    auto store=[&]() {
        *reinterpret_cast<uint4*>(&sA[sr][8*sq])=ra0;
        if constexpr(!Wide){
            *reinterpret_cast<uint4*>(&sA[sr+32][8*sq])=ra1;
            *reinterpret_cast<uint4*>(&sA[sr+64][8*sq])=ra2;
            *reinterpret_cast<uint4*>(&sA[sr+96][8*sq])=ra3;
        }
        *reinterpret_cast<uint4*>(&sB[sr][8*sq])=rb0;
        *reinterpret_cast<uint4*>(&sB[sr+STEP][8*sq])=rb1;
        *reinterpret_cast<uint4*>(&sB[sr+2*STEP][8*sq])=rb2;
        *reinterpret_cast<uint4*>(&sB[sr+3*STEP][8*sq])=rb3;
    };
    f8 acc[4][TN];
#pragma unroll
    for(int i=0;i<4;i++)
#pragma unroll
        for(int j=0;j<TN;j++)acc[i][j]=f8{0,0,0,0,0,0,0,0};
    load(0);store();__syncthreads();
    const int ar=64*wm+l16,br=WN*wn+l16;
    for(int k0=0;k0<K;k0+=KT){
        const bool more=k0+KT<K;
        if(more)load(k0+KT);
#pragma unroll
        for(int ks=0;ks<KT;ks+=16){
            const h16 a0=frag(&sA[ar][ks]),a1=frag(&sA[ar+16][ks]),a2=frag(&sA[ar+32][ks]),a3=frag(&sA[ar+48][ks]);
            const h16 b0=frag(&sB[br][ks]),b1=frag(&sB[br+16][ks]);
#define TILE_ROW2(i,a) \
    acc[i][0]=__builtin_amdgcn_wmma_f32_16x16x16_f16_w32(a,b0,acc[i][0]); \
    acc[i][1]=__builtin_amdgcn_wmma_f32_16x16x16_f16_w32(a,b1,acc[i][1]);
            if constexpr(Wide){
                const h16 b2=frag(&sB[br+32][ks]),b3=frag(&sB[br+48][ks]);
#define TILE_ROW4(i,a) \
    TILE_ROW2(i,a) \
    acc[i][2]=__builtin_amdgcn_wmma_f32_16x16x16_f16_w32(a,b2,acc[i][2]); \
    acc[i][3]=__builtin_amdgcn_wmma_f32_16x16x16_f16_w32(a,b3,acc[i][3]);
                TILE_ROW4(0,a0) TILE_ROW4(1,a1) TILE_ROW4(2,a2) TILE_ROW4(3,a3)
#undef TILE_ROW4
            } else {TILE_ROW2(0,a0) TILE_ROW2(1,a1) TILE_ROW2(2,a2) TILE_ROW2(3,a3)}
#undef TILE_ROW2
        }
        if(more){__syncthreads();store();__syncthreads();}
    }
#pragma unroll
    for(int i=0;i<4;i++)
#pragma unroll
        for(int j=0;j<TN;j++){
            const int n=n0+WN*wn+16*j+l16;if(n>=N)continue;
#pragma unroll
            for(int e=0;e<8;e++){
                const int m=m0+64*wm+16*i+2*e+hi;
                if(m<M){float* y=Y+(size_t)m*ldy+n;*y=accumulate?*y+acc[i][j][e]:acc[i][j][e];}
            }
        }
}
} // namespace pfg
