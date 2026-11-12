// Replay the native Q8 path with its real packed registration and large rotating
// weight banks. Logical payload bandwidth is NOT measured physical DRAM traffic.
#include "strata/kernels/native_mmvq.hpp"
#include "strata/core/dispatch_stats.hpp"
#include <cuda_runtime.h>
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <filesystem>
#include <random>
#include <string>
#include <unistd.h>
#include <vector>
namespace K = strata::kernels;
void ck(cudaError_t e) { if(e != cudaSuccess) { std::fprintf(stderr,"%s\n",cudaGetErrorString(e)); std::exit(2); } }
long evicted() {
    const auto path=std::filesystem::path("/sys/class/kfd/kfd/proc")/std::to_string(getpid());
    long sum=0;bool seen=false;
    if(std::filesystem::exists(path))for(const auto& e:std::filesystem::directory_iterator(path)) {
        std::ifstream f(e.path()/"evicted_ms");long v;
        if(f>>v){sum+=v;seen=true;}
    }
    return seen?sum:-1;
}
float half(uint16_t bits) { _Float16 h; std::memcpy(&h,&bits,2); return (float)h; }
struct Shape { const char* label; int ni,no; };
int main() {
    const Shape shapes[]={{"gdn_qkv",2560,10240},{"gdn_gate",2560,6144},
        {"out",6144,2560},{"qsa_q",2560,12288},{"qsa_kv",2560,512},
        {"shared_gu",2560,640},{"shared_down",640,2560},{"head",2560,248320}};
    std::mt19937 rng(7);
    cudaStream_t st; ck(cudaStreamCreate(&st)); cudaEvent_t b,e; ck(cudaEventCreate(&b));ck(cudaEventCreate(&e));
    for(const auto&s:shapes) {
        const size_t bytes=(size_t)s.ni*s.no/32*34;
        const int copies=std::max<size_t>(1,((size_t(128)<<20)+bytes-1)/bytes);
        // NativeDense registers the eligible projections. NativeHead is loaded
        // separately and is not packed on gfx1151 (the head's pack hook is SM60).
        const bool packed=std::strcmp(s.label,"head")!=0&&K::native_q8_0_packed_enabled()&&K::native_q8_0_packed_eligible(s.ni,s.no);
        std::vector<uint8_t> host(bytes),pack(bytes);
        for(size_t j=0;j<bytes;j+=34) {host[j]=0x1f;host[j+1]=0x21;for(int k=0;k<32;k++)host[j+2+k]=rng()&255;}
        if(packed)K::native_q8_0_pack_host(host.data(),pack.data(),s.ni,s.no);
        std::vector<void*> w(copies),wp(copies,nullptr);
        for(int j=0;j<copies;j++) {
            ck(cudaMalloc(&w[j],bytes));ck(cudaMemcpy(w[j],host.data(),bytes,cudaMemcpyHostToDevice));
            if(packed){ck(cudaMalloc(&wp[j],bytes));ck(cudaMemcpy(wp[j],pack.data(),bytes,cudaMemcpyHostToDevice));K::native_q8_0_packed_register(w[j],wp[j],s.ni,s.no);}
        }
        std::vector<float> hx(s.ni*4),hy(s.no*4);
        for(auto&v:hx)v=std::normal_distribution<float>(0,1)(rng);
        float *x,*y;void*xq; ck(cudaMalloc(&x,hx.size()*4));ck(cudaMemcpy(x,hx.data(),hx.size()*4,cudaMemcpyHostToDevice));
        ck(cudaMalloc(&y,hy.size()*4));const size_t qbytes=K::native_q8_1_bytes(s.ni,4);ck(cudaMalloc(&xq,qbytes));
        std::vector<uint8_t> q(qbytes);
        for(int c:{1,3,4}) {
            K::native_quantize_q8_1(x,xq,s.ni,c,st);
            K::native_mmvq(8,w[0],xq,y,s.ni,s.no,c,st);ck(cudaStreamSynchronize(st));
            ck(cudaMemcpy(hy.data(),y,s.no*c*4,cudaMemcpyDeviceToHost));ck(cudaMemcpy(q.data(),xq,qbytes,cudaMemcpyDeviceToHost));
            // CPU reference uses the same quantized activation, independently
            // decoding all blocks of first/middle/final output rows, every column.
            double max_error=0,max_normalized=0;
            for(int col=0;col<c;col++)for(int row:{0,s.no/2,s.no-1}) {
                double sum=0,l1=0;
                for(int block=0;block<s.ni/32;block++) {
                    size_t wo=((size_t)row*s.ni/32+block)*34, xo=((size_t)col*s.ni/32+block)*36;
                    uint16_t wd,xd;std::memcpy(&wd,&host[wo],2);std::memcpy(&xd,&q[xo],2);
                    for(int k=0;k<32;k++) {double v=(double)half(wd)*half(xd)*(int8_t)host[wo+2+k]*(int8_t)q[xo+4+k];sum+=v;l1+=std::abs(v);}
                }
                double err=std::abs((double)hy[(size_t)col*s.no+row]-sum);max_error=std::max(max_error,err);
                max_normalized=std::max(max_normalized,err/std::max(1.,l1));
                if(!std::isfinite(hy[(size_t)col*s.no+row]) || err>1e-5*std::max(1.,l1)){std::fprintf(stderr,"CPU mismatch %s c%d row%d got%g want%g\n",s.label,c,row,hy[(size_t)col*s.no+row],sum);return 3;}
            }
            std::printf("{\"kind\":\"reference\",\"shape\":\"%s\",\"cols\":%d,\"sampled_outputs\":%d,\"max_error\":%.9g,\"max_error_over_l1\":%.9g,\"passed\":true}\n",s.label,c,c*3,max_error,max_normalized);
            if(packed) {
                K::native_q8_0_packed_unregister(w[0]);
                K::native_mmvq(8,w[0],xq,y,s.ni,s.no,c,st);ck(cudaStreamSynchronize(st));
                std::vector<float> raw(s.no*c);ck(cudaMemcpy(raw.data(),y,raw.size()*4,cudaMemcpyDeviceToHost));
                size_t different=0;for(size_t j=0;j<raw.size();j++)if(std::memcmp(&raw[j],&hy[j],4))different++;
                std::printf("{\"kind\":\"packed_parity\",\"shape\":\"%s\",\"cols\":%d,\"outputs\":%zu,\"different\":%zu}\n",s.label,c,raw.size(),different);
                if(different)return 4;
                K::native_q8_0_packed_register(w[0],wp[0],s.ni,s.no);
            }
            // Full bank traversal, not a cache-resident repeated matrix.
            const int iters=copies*3;
            for(int trial=0;trial<7;trial++) {
                long ev0=evicted();ck(cudaEventRecord(b,st));
                for(int j=0;j<iters;j++)K::native_mmvq(8,w[j%copies],xq,y,s.ni,s.no,c,st);
                ck(cudaEventRecord(e,st));ck(cudaEventSynchronize(e));float ms;ck(cudaEventElapsedTime(&ms,b,e));long ev1=evicted();
                std::printf("{\"kind\":\"timing\",\"shape\":\"%s\",\"n_in\":%d,\"n_out\":%d,\"cols\":%d,\"packed\":%s,\"bytes\":%zu,\"copies\":%d,\"trial\":%d,\"iters\":%d,\"ms_per_call\":%.9g,\"logical_GB_s\":%.9g,\"self_evicted_ms\":%ld}\n",s.label,s.ni,s.no,c,packed?"true":"false",bytes,copies,trial,iters,ms/iters,bytes*iters/(ms*1e6),ev0<0||ev1<0?-1:ev1-ev0);
            }
        }
        for(int j=0;j<copies;j++){K::native_q8_0_packed_unregister(w[j]);if(wp[j])ck(cudaFree(wp[j]));ck(cudaFree(w[j]));}
        ck(cudaFree(x));ck(cudaFree(y));ck(cudaFree(xq));
    }
    strata::dispatch::Stats::get().write_report();
    ck(cudaEventDestroy(b));ck(cudaEventDestroy(e));ck(cudaStreamDestroy(st));
}
