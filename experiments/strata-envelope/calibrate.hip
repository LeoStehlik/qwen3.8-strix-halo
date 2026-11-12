// Independent gfx1151 calibration. Requested bytes are not DRAM counters.
#include <hip/hip_runtime.h>
#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <string>
#include <vector>
#include <unistd.h>

void ck(hipError_t e) { if(e != hipSuccess) { std::fprintf(stderr,"%s\n",hipGetErrorString(e)); std::exit(2); } }
template<class T> T* alloc(size_t n) { T* p; ck(hipMalloc(&p,n*sizeof(T))); return p; }
long evicted() {
    long sum=0; const auto dir=std::filesystem::path("/sys/class/kfd/kfd/proc")/std::to_string(getpid());
    if(std::filesystem::exists(dir)) for(const auto& x:std::filesystem::directory_iterator(dir)) {
        std::ifstream f(x.path()/"evicted_ms"); long v=0; if(f>>v) sum+=v;
    }
    return sum;
}
__global__ void initialize(uint4* a,uint4* b,uint4* c,size_t n) {
    for(size_t i=(size_t)blockIdx.x*blockDim.x+threadIdx.x;i<n;i+=(size_t)gridDim.x*blockDim.x) {
        a[i]=make_uint4(1,2,3,4); b[i]=make_uint4(5,6,7,8); c[i]=make_uint4(0,0,0,0);
    }
}
template<bool PERMUTED> __global__ void read_reduce(const uint4* __restrict__ a,unsigned long long* __restrict__ o,size_t n) {
    const size_t tid=(size_t)blockIdx.x*blockDim.x+threadIdx.x, step=(size_t)gridDim.x*blockDim.x;
    uint4 sum=make_uint4(0,0,0,0);
    for(size_t i=tid;i<n;i+=step) {
        // A permutation of 16 KiB tiles, preserving coalescing within each tile.
        const size_t j=PERMUTED ? (((i/1024*104729)&(n/1024-1))*1024+i%1024) : i;
        const uint4 v=a[j]; sum.x+=v.x;sum.y+=v.y;sum.z+=v.z;sum.w+=v.w;
    }
    o[tid]=(unsigned long long)sum.x+sum.y+sum.z+sum.w;
}
template<bool ADD> __global__ void mixed(const uint4* __restrict__ a,const uint4* __restrict__ b,uint4* __restrict__ c,size_t n) {
    for(size_t i=(size_t)blockIdx.x*blockDim.x+threadIdx.x;i<n;i+=(size_t)gridDim.x*blockDim.x) {
        const uint4 u=a[i];
        if constexpr(ADD) {const uint4 v=b[i]; c[i]=make_uint4(u.x+v.x,u.y+v.y,u.z+v.z,u.w+v.w);}
        else c[i]=u;
    }
}
__global__ void validate_memory(const uint4* a,size_t n,bool add,unsigned* errors) {
    for(size_t i=(size_t)blockIdx.x*blockDim.x+threadIdx.x;i<n;i+=(size_t)gridDim.x*blockDim.x) {
        const auto x=a[i];
        if(x.x!=(add?6u:1u)||x.y!=(add?8u:2u)||x.z!=(add?10u:3u)||x.w!=(add?12u:4u)) atomicAdd(errors,1u);
    }
}
template<int KIND> __global__ void vector_compute(float* out,int* iout,int loops,float mul,float add,int aa,int bb) {
    const int tid=blockIdx.x*blockDim.x+threadIdx.x;
    float f[8]; int d[8];
#pragma unroll
    for(int j=0;j<8;j++){f[j]=(tid%31+j+1)*0.001f;d[j]=tid%31+j;}
    for(int i=0;i<loops;i++) {
#pragma unroll
        for(int j=0;j<8;j++) {
            if constexpr(KIND==0) f[j]=__builtin_fmaf(f[j],mul,add);
            else d[j]=__builtin_amdgcn_sudot4(true,aa,true,bb,d[j],false);
        }
    }
#pragma unroll
    for(int j=0;j<8;j++) {if constexpr(KIND==0) out[(size_t)tid*8+j]=f[j]; else iout[(size_t)tid*8+j]=d[j];}
}
using h16=_Float16 __attribute__((ext_vector_type(16)));
using f8=float __attribute__((ext_vector_type(8)));
__global__ void matrix_compute(float* out,int loops,float value) {
    const int tid=blockIdx.x*blockDim.x+threadIdx.x;
    h16 a,b; f8 c0,c1;
#pragma unroll
    for(int j=0;j<16;j++){a[j]=(_Float16)value;b[j]=(_Float16)value;}
#pragma unroll
    for(int j=0;j<8;j++){c0[j]=0;c1[j]=1;}
    for(int i=0;i<loops;i++) {
        c0=__builtin_amdgcn_wmma_f32_16x16x16_f16_w32(a,b,c0);
        c1=__builtin_amdgcn_wmma_f32_16x16x16_f16_w32(a,b,c1);
    }
#pragma unroll
    for(int j=0;j<8;j++){out[(size_t)tid*16+j]=c0[j];out[(size_t)tid*16+j+8]=c1[j];}
}
struct Timer {
    hipEvent_t a,b; Timer(){ck(hipEventCreate(&a));ck(hipEventCreate(&b));}
    ~Timer(){(void)hipEventDestroy(a);(void)hipEventDestroy(b);}
    template<class F> float run(F f) {ck(hipEventRecord(a));f();ck(hipGetLastError());ck(hipEventRecord(b));ck(hipEventSynchronize(b));float ms;ck(hipEventElapsedTime(&ms,a,b));return ms;}
};
int main(int argc,char** argv) {
    setvbuf(stdout,nullptr,_IOLBF,0);
    const std::string mode=argc>1?argv[1]:"all";
    if(mode!="all"&&mode!="memory"&&mode!="compute"&&mode!="counter") return 8;
    hipDeviceProp_t p{};ck(hipGetDeviceProperties(&p,0));
    if(std::string(p.gcnArchName).find("gfx1151")==std::string::npos) return 3;
    std::printf("{\"kind\":\"device\",\"arch\":\"%s\",\"hip_multiprocessor_count\":%d,\"wave_size\":%d,\"clock_khz_reported\":%d,\"memory_clock_khz_reported\":%d,\"bus_bits_reported\":%d}\n",p.gcnArchName,p.multiProcessorCount,p.warpSize,p.clockRate,p.memoryClockRate,p.memoryBusWidth);
    Timer timer;
    const size_t counter_mib=argc>2?std::stoul(argv[2]):512;
    if(counter_mib<2||counter_mib>2048||(counter_mib&(counter_mib-1)))return 9;
    const std::vector<size_t> sizes=mode=="counter"?std::vector<size_t>{counter_mib}:std::vector<size_t>{64,512,2048};
    if(mode=="all"||mode=="memory"||mode=="counter") for(size_t mib:sizes) {
        const size_t bytes=mib*1024*1024,n=bytes/16;
        auto a=alloc<uint4>(n),b=alloc<uint4>(n),c=alloc<uint4>(n);
        auto sums=alloc<unsigned long long>(5120*256);auto errors=alloc<unsigned>(1);
        initialize<<<1280,256>>>(a,b,c,n);ck(hipDeviceSynchronize());
        for(int trial=0;trial<7;trial++) for(int gi=0;gi<3;gi++) {
            const unsigned grid=(unsigned[]){320,1280,5120}[(trial%2)?2-gi:gi];
            for(int mi=0;mi<4;mi++) {
                const int kind=(trial%2)?3-mi:mi;
                auto launch=[&](){if(kind==0) read_reduce<false><<<grid,256>>>(a,sums,n);
                    if(kind==1) read_reduce<true><<<grid,256>>>(a,sums,n);
                    if(kind==2) mixed<false><<<grid,256>>>(a,b,c,n);
                    if(kind==3) mixed<true><<<grid,256>>>(a,b,c,n);};
                if(trial==0){launch();launch();ck(hipDeviceSynchronize());}
                const long before=evicted();const float ms=timer.run(launch);const long delta=evicted()-before;
                if(trial==0) {
                    if(kind<2) {std::vector<unsigned long long> h(grid*256);ck(hipMemcpy(h.data(),sums,h.size()*8,hipMemcpyDeviceToHost));unsigned long long sum=0;for(auto v:h)sum+=v;if(sum!=n*10) return 4;}
                    else {ck(hipMemset(errors,0,4));validate_memory<<<1280,256>>>(c,n,kind==3,errors);unsigned e;ck(hipMemcpy(&e,errors,4,hipMemcpyDeviceToHost));if(e)return 5;}
                }
                const char* label=(const char*[]){"read_linear","read_permuted_tiles","copy","add_two_inputs"}[kind];
                const size_t requested=bytes*(kind<2?1:kind==2?2:3);
                std::printf("{\"kind\":\"memory\",\"op\":\"%s\",\"mib_per_buffer\":%zu,\"grid\":%u,\"trial\":%d,\"ms\":%.6f,\"requested_bytes\":%zu,\"requested_gb_s\":%.6f,\"evicted_ms\":%ld}\n",label,mib,grid,trial,ms,requested,requested/(ms*1e6),delta);
            }
        }
        ck(hipFree(a));ck(hipFree(b));ck(hipFree(c));ck(hipFree(sums));ck(hipFree(errors));
    }
    if(mode=="all"||mode=="compute") {
        auto f=alloc<float>(1280*256*16);auto d=alloc<int>(1280*256*8);
        const int loops=4096; const float mul=1.000001f,add=0.00001f;
        for(int trial=0;trial<7;trial++) for(unsigned grid:{80u,320u,1280u}) for(int kind=0;kind<3;kind++) {
            auto launch=[&](){if(kind==0)vector_compute<0><<<grid,256>>>(f,d,loops,mul,add,0x01020304,0x01010101);
                if(kind==1)vector_compute<1><<<grid,256>>>(f,d,loops,mul,add,0x01020304,0x01010101);
                if(kind==2)matrix_compute<<<grid,256>>>(f,loops,0.25f);};
            if(trial==0){launch();ck(hipDeviceSynchronize());}
            const long before=evicted();const float ms=timer.run(launch);const long delta=evicted()-before;
            if(trial==0) {
                if(kind==1){std::vector<int> h(grid*256*8);ck(hipMemcpy(h.data(),d,h.size()*4,hipMemcpyDeviceToHost));for(size_t i=0;i<h.size();i++)if(h[i]!=int(i/8%31+i%8)+loops*10)return 6;}
                else {const size_t stride=kind==0?8:16;std::vector<float> h(grid*256*stride);ck(hipMemcpy(h.data(),f,h.size()*4,hipMemcpyDeviceToHost));
                    float expected[31][8];for(int t=0;t<31;t++)for(int j=0;j<8;j++){float v=(t+j+1)*0.001f;for(int it=0;it<loops;it++)v=std::fma(v,mul,add);expected[t][j]=v;}
                    for(size_t i=0;i<h.size();i++){float ref=kind==0?expected[i/8%31][i%8]:float(loops+(i%16>=8));if(!std::isfinite(h[i])||std::abs(h[i]-ref)>1e-5f) return 7;}}
            }
            const double ops=kind==2?double(grid)*8*loops*2*8192:double(grid)*256*loops*8*(kind==0?2:8);
            const char* label=(const char*[]){"fp32_fma8","signed_dot4x8","fp16_wmma2"}[kind];
            std::printf("{\"kind\":\"compute\",\"op\":\"%s\",\"grid\":%u,\"trial\":%d,\"loops\":%d,\"ms\":%.6f,\"scalar_operations\":%.0f,\"teraops_s\":%.6f,\"evicted_ms\":%ld}\n",label,grid,trial,loops,ms,ops,ops/(ms*1e9),delta);
        }
        ck(hipFree(f));ck(hipFree(d));
    }
    std::puts("{\"kind\":\"validation\",\"passed\":true}");
}
