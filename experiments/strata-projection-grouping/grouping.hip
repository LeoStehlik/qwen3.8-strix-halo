// Isolated launch-order screen of the existing padded FP16 projection kernel.
// The generated header changes only its compile-time block grouping.
#include "wmma_gemm_grouping.generated.cuh"
#ifdef PROJECTION_TILE_SCREEN
#include "tile-kernels.cuh"
#endif
#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <vector>

#define CK(x) do { auto e=(x); if(e!=hipSuccess) { fprintf(stderr,"%s: %s\n",#x,hipGetErrorString(e)); exit(2); } } while(0)

__global__ void initialize(_Float16* p, size_t count, unsigned salt) {
    size_t i=(size_t)blockIdx.x*blockDim.x+threadIdx.x;
    if(i<count) { unsigned x=(unsigned)i+salt; x^=x>>16; x*=0x7feb352du; x^=x>>15; x*=0x846ca68bu; x^=x>>16;
        p[i]=(_Float16)((int)(x%513)-256)/(_Float16)512; }
}
__global__ void fill(float* p,size_t n) {
    size_t i=(size_t)blockIdx.x*blockDim.x+threadIdx.x; if(i<n)p[i]=0.25f;
}
__global__ void compare(const float* a,const float* b,size_t n,unsigned long long* bad) {
    size_t i=(size_t)blockIdx.x*blockDim.x+threadIdx.x;
    if(i<n && (__float_as_uint(a[i])!=__float_as_uint(b[i]) || !isfinite(a[i])))atomicAdd(bad,1ULL);
}
void launch(int group,const _Float16* x,const _Float16* w,float* y,int m,int n,int k,int ldy,int acc,int ldx,int ldw) {
    unsigned grid=((m+127)/128)*((n+255)/256);
#define GO(G) case G: pfg::kernel_bk64<G><<<grid,256>>>(x,w,y,m,n,k,ldy,acc,ldx,ldw); break
    switch(group) {GO(1);GO(2);GO(4);GO(8);GO(16);GO(32);GO(64);
#ifdef PROJECTION_ROW_STREAM
        case 99: pfg::kernel_bk64_rowstream<<<grid,256>>>(x,w,y,m,n,k,ldy,acc,ldx,ldw);break;
#endif
#ifdef PROJECTION_TILE_SCREEN
        case 128: pfg::kernel_tile<false><<<((m+127)/128)*((n+127)/128),256>>>(x,w,y,m,n,k,ldy,acc,ldx,ldw);break;
        case 512: pfg::kernel_tile<true><<<((m+127)/128)*((n+511)/512),512>>>(x,w,y,m,n,k,ldy,acc,ldx,ldw);break;
#endif
        default:exit(3);}
#undef GO
    CK(hipGetLastError());
}

void run(int m,int n,int k,int xpad,int reps,bool cpu,int acc=0) {
    int ldx=k+xpad,ldw=k+64,ldy=n+(cpu?7:0);
    size_t nx=(size_t)m*ldx,nw=(size_t)n*ldw,ny=(size_t)m*ldy;
    _Float16 *x,*w;float *y,*ref;unsigned long long* bad;
    CK(hipMalloc(&x,nx*2));CK(hipMalloc(&w,nw*2));CK(hipMalloc(&y,ny*4));CK(hipMalloc(&ref,ny*4));CK(hipMalloc(&bad,8));
    initialize<<<(nx+255)/256,256>>>(x,nx,19);initialize<<<(nw+255)/256,256>>>(w,nw,37);
    fill<<<(ny+255)/256,256>>>(ref,ny); CK(hipGetLastError());
    launch(8,x,w,ref,m,n,k,ldy,acc,ldx,ldw);CK(hipDeviceSynchronize());
    if(cpu) {
        std::vector<_Float16> hx(nx),hw(nw);std::vector<float> hy(ny);
        CK(hipMemcpy(hx.data(),x,nx*2,hipMemcpyDeviceToHost));CK(hipMemcpy(hw.data(),w,nw*2,hipMemcpyDeviceToHost));
        CK(hipMemcpy(hy.data(),ref,ny*4,hipMemcpyDeviceToHost));size_t failures=0,nonidentical=0;double max_abs=0;
        for(int r=0;r<m;r++)for(int c=0;c<ldy;c++) {
            double v=0;
            if(c<n){for(int z=0;z<k;z++)v+=(double)hx[(size_t)r*ldx+z]*(double)hw[(size_t)c*ldw+z];if(acc)v+=0.25;}
            else v=0.25;
            float want=(float)v;float got=hy[(size_t)r*ldy+c];double delta=fabs((double)got-v);
            if(memcmp(&want,&got,4))nonidentical++;
            max_abs=std::max(max_abs,delta);
            // The unchanged WMMA control is not bitwise identical to a host
            // double sum on these full-mantissa inputs. Bound CPU error here;
            // all scheduling candidates must still match the GPU bit for bit.
            if(!std::isfinite(got) || delta>1e-6 || (c>=n && got!=0.25f)){
                if(failures<8)fprintf(stderr,"CPU mismatch row=%d col=%d got=%.9g want=%.9g delta=%.9g\n",r,c,hy[(size_t)r*ldy+c],want,hy[(size_t)r*ldy+c]-want);
                failures++;
            }
        }
        printf("{\"kind\":\"cpu_reference\",\"m\":%d,\"n\":%d,\"k\":%d,\"acc\":%d,\"nonidentical\":%zu,\"max_abs\":%.12g,\"atol\":1e-6,\"failures\":%zu}\n",m,n,k,acc,nonidentical,max_abs,failures);
        if(failures)exit(4);
    }
#ifdef PROJECTION_ROW_STREAM
    const int groups[]={8,99};
#elif defined(PROJECTION_TILE_SCREEN)
    const int groups[]={8,128,512};
#else
    const int groups[]={1,2,4,8,16,32,64};
#endif
    constexpr int ngroups=sizeof(groups)/sizeof(groups[0]);
    for(int g:groups){
        fill<<<(ny+255)/256,256>>>(y,ny);launch(g,x,w,y,m,n,k,ldy,acc,ldx,ldw);CK(hipMemset(bad,0,8));
        compare<<<(ny+255)/256,256>>>(y,ref,ny,bad);CK(hipGetLastError());unsigned long long failures;
        CK(hipMemcpy(&failures,bad,8,hipMemcpyDeviceToHost));
        printf("{\"kind\":\"parity\",\"m\":%d,\"n\":%d,\"k\":%d,\"acc\":%d,\"group\":%d,\"elements\":%zu,\"mismatches\":%llu}\n",m,n,k,acc,g,ny,failures);
        if(failures)exit(5);
    }
    hipEvent_t begin,end;CK(hipEventCreate(&begin));CK(hipEventCreate(&end));
    // Rotate and reverse group order each round so one setting is not always
    // measured first. Output comparison above is outside the timing window.
    for(int round=0;round<reps;round++)for(int j=0;j<ngroups;j++){
        int idx=(round+(round%2?-j:j)+ngroups)%ngroups;int g=groups[idx];
        CK(hipEventRecord(begin));launch(g,x,w,y,m,n,k,ldy,0,ldx,ldw);CK(hipEventRecord(end));CK(hipEventSynchronize(end));
        float ms;CK(hipEventElapsedTime(&ms,begin,end));
        printf("{\"kind\":\"timing\",\"m\":%d,\"n\":%d,\"k\":%d,\"xpad\":%d,\"group\":%d,\"round\":%d,\"ms\":%.6f}\n",m,n,k,xpad,g,round,ms);
    }
    CK(hipEventDestroy(begin));CK(hipEventDestroy(end));CK(hipFree(x));CK(hipFree(w));CK(hipFree(y));CK(hipFree(ref));CK(hipFree(bad));
}
int main(int argc,char** argv) {
    setvbuf(stdout,nullptr,_IOLBF,0);
    if(argc==2 && strcmp(argv[1],"--check")==0) {
        for(int acc=0;acc<2;acc++){run(129,1031,64,64,0,true,acc);run(2049,1025,64,0,0,true,acc);}
    } else if(argc==5) run(16384,atoi(argv[1]),atoi(argv[2]),atoi(argv[3]),atoi(argv[4]),false);
    else {fprintf(stderr,"usage: grouping --check | N K Xpad rounds\n");return 1;}
    return 0;
}
