// Isolated scheduling experiment. Reference kernels are extracted by build.py.
// Strata / llama.cpp reference code is MIT licensed; see the pinned source tree.
#include "reference.hpp"
#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <numeric>
#include <random>
#include <string>
#include <vector>
#include <unistd.h>

// Same 40 partial dots and the lane-zero addition tree of the 32-lane kernel.
// No weight conversion, no changed quantization, and no cross-entry reuse.
template<int LANES>
__device__ __forceinline__ float dot_sub(const uint8_t* row, const block_q8_1* x, int t) {
    float a = 0.0f;
    a += Fmt<7>::dot(row, x + t / 2, t / 2, 2 * (t % 2));
    if (t < 8) a += Fmt<7>::dot(row, x + (t + 32) / 2, (t + 32) / 2, 2 * (t % 2));
    float b = 0.0f;
    b += Fmt<7>::dot(row, x + (t + 16) / 2, (t + 16) / 2, 2 * (t % 2));
    a = __fadd_rn(a, b);
    if constexpr (LANES == 8) {
        float c = 0.0f, d = 0.0f;
        c += Fmt<7>::dot(row, x + (t + 8) / 2, (t + 8) / 2, 2 * (t % 2));
        d += Fmt<7>::dot(row, x + (t + 24) / 2, (t + 24) / 2, 2 * (t % 2));
        a = __fadd_rn(a, __fadd_rn(c, d));
    }
    for (int o = LANES / 2; o; o >>= 1) a += __shfl_xor_sync(0xffffffffu, a, o);
    return a;
}

template<int LANES>
__global__ __launch_bounds__(256) void q51_subwarp(
        const unsigned long long* __restrict__ ptr, const int32_t* __restrict__ starts,
        const int32_t* __restrict__ ng, const int32_t* __restrict__ dst,
        const block_q8_1* __restrict__ x, NativeExpertLayout L, float* __restrict__ out) {
    const int r = blockIdx.x * (256 / LANES) + threadIdx.x / LANES;
    if (r >= L.n_embd) return;
    const int t = threadIdx.x % LANES;
    for (int g = blockIdx.y; g < *ng; g += gridDim.y) {
        const auto* row = (const uint8_t*) ptr[g] + L.down_off + r * L.d_row;
        for (int e = starts[g]; e < starts[g + 1]; ++e) {
            const float v = dot_sub<LANES>(row, x + e * 20, t);
            if (t == 0) out[(size_t) dst[e] * L.n_embd + r] = v;
        }
    }
}

void ck(hipError_t e) {
    if (e != hipSuccess) { std::fprintf(stderr, "%s\n", hipGetErrorString(e)); std::exit(2); }
}
template<class T> T* alloc(size_t n) { T* p; ck(hipMalloc(&p, sizeof(T) * n)); return p; }
template<class T> void upload(T* p, const std::vector<T>& v) {
    ck(hipMemcpy(p, v.data(), sizeof(T) * v.size(), hipMemcpyHostToDevice));
}
long evicted_ms() {
    long total = 0;
    const auto directory = std::filesystem::path("/sys/class/kfd/kfd/proc") / std::to_string(getpid());
    for (const auto& item : std::filesystem::directory_iterator(directory)) {
        std::ifstream f(item.path() / "evicted_ms"); long n;
        if (f >> n) total += n;
    }
    return total;
}
struct Case {
    NativeExpertLayout L;
    int groups, entries, grid_groups, banks, output_rows;
    std::vector<uint8_t> weights;
    std::vector<block_q8_1> inputs;
    std::vector<int32_t> starts, dest;
    uint8_t* dw;
    unsigned long long* dp;
    int32_t *ds, *dn, *dd;
    block_q8_1* dx;
    float* dy;
    long timed_evicted_ms = 0;
    Case(const std::vector<int>& counts, int rows, int gy, int bank_count, int seed)
        : groups(counts.size()), grid_groups(gy), banks(bank_count) {
        static_assert(sizeof(block_q5_1) == 24 && sizeof(block_q8_1) == 36);
        L.n_embd = rows; L.n_ff = 640; L.d_type = 7; L.d_row = 20 * sizeof(block_q5_1);
        // Deliberately exercise nonzero down offsets as real blobs do.
        L.down_off = 256; L.bytes = L.down_off + L.d_row * rows;
        starts.push_back(0);
        for (int c : counts) starts.push_back(starts.back() + c);
        entries = starts.back(); output_rows = 2 * entries + 5;
        std::mt19937 rng(seed);
        weights.resize(std::max(1, groups) * banks * L.bytes);
        for (auto& b : weights) b = uint8_t(rng());
        for (int g = 0; g < std::max(1, groups) * banks; ++g) {
            auto* w = (block_q5_1*)(weights.data() + g * L.bytes + L.down_off);
            for (int b = 0; b < rows * 20; ++b) {
                // All 5-bit codes occur; finite signed scales with a wide range.
                w[b].dm = __halves2half2(__float2half((int(rng() % 255) - 127) / 8192.0f),
                                         __float2half((int(rng() % 255) - 127) / 8192.0f));
            }
        }
        inputs.resize(std::max(1, entries) * 20);
        for (auto& b : inputs) {
            b.ds = __halves2half2(__float2half((1 + rng() % 127) / 4096.0f), __float2half(0));
            for (auto& q : b.qs) q = int8_t(int(rng() % 255) - 127);
        }
        dest.resize(std::max(1, entries));
        for (int e = 0; e < entries; ++e) dest[e] = 2 * e + 1;
        std::shuffle(dest.begin(), dest.begin() + entries, rng);
        dw = alloc<uint8_t>(weights.size()); upload(dw, weights);
        std::vector<unsigned long long> ptr(std::max(1, groups) * banks);
        for (size_t i = 0; i < ptr.size(); ++i) ptr[i] = (unsigned long long)(dw + i * L.bytes);
        dp = alloc<unsigned long long>(ptr.size()); upload(dp, ptr);
        ds = alloc<int32_t>(starts.size()); upload(ds, starts);
        dn = alloc<int32_t>(1); ck(hipMemcpy(dn, &groups, 4, hipMemcpyHostToDevice));
        dd = alloc<int32_t>(dest.size()); upload(dd, dest);
        dx = alloc<block_q8_1>(inputs.size()); upload(dx, inputs);
        dy = alloc<float>((size_t) output_rows * rows);
    }
    ~Case() { ck(hipFree(dw)); ck(hipFree(dp)); ck(hipFree(ds)); ck(hipFree(dn)); ck(hipFree(dd)); ck(hipFree(dx)); ck(hipFree(dy)); }
    void launch(int lanes, int bank, hipStream_t s) {
        const auto* ptr = dp + bank * std::max(1, groups);
        dim3 grid((L.n_embd + 256 / lanes - 1) / (256 / lanes), grid_groups);
        if (lanes == 32) native_down_kernel<7><<<grid, 256, 0, s>>>(ptr, ds, dn, dd, dx, L, dy);
        else if (lanes == 16) q51_subwarp<16><<<grid, 256, 0, s>>>(ptr, ds, dn, dd, dx, L, dy);
        else q51_subwarp<8><<<grid, 256, 0, s>>>(ptr, ds, dn, dd, dx, L, dy);
        ck(hipGetLastError());
    }
    std::vector<float> result(int lanes, int bank, hipStream_t s) {
        ck(hipMemset(dy, 0xff, (size_t) output_rows * L.n_embd * 4));
        launch(lanes, bank, s); ck(hipStreamSynchronize(s));
        std::vector<float> v((size_t) output_rows * L.n_embd);
        ck(hipMemcpy(v.data(), dy, v.size() * 4, hipMemcpyDeviceToHost)); return v;
    }
    double reference(int group, int entry, int row) const {
        auto* w = (const block_q5_1*)(weights.data() + group * L.bytes + L.down_off + row * L.d_row);
        double sum = 0;
        for (int b = 0; b < 20; ++b) {
            uint32_t high; std::memcpy(&high, w[b].qh, 4);
            for (int i = 0; i < 32; ++i) {
                int v = ((w[b].qs[i % 16] >> (i < 16 ? 0 : 4)) & 15) | (((high >> i) & 1) << 4);
                double weight = double(__low2float(w[b].dm)) * v + __high2float(w[b].dm);
                const auto& x = inputs[entry * 20 + b];
                sum += weight * double(__low2float(x.ds)) * int(x.qs[i]);
            }
        }
        return sum;
    }
    bool check(hipStream_t s) {
        const auto control = result(32, 0, s);
        bool good = true;
        for (int lanes : {8, 16}) {
            const auto v = result(lanes, 0, s);
            size_t diff = 0;
            for (size_t i = 0; i < v.size(); ++i) diff += std::memcmp(&v[i], &control[i], 4) != 0;
            if (diff) { good = false; std::fprintf(stderr, "lanes=%d: %zu bit mismatches\n", lanes, diff); }
        }
        // Independent dequantize + double dot, first/middle/final rows of every entry.
        double err = 0, den = 0;
        std::vector<bool> owned(output_rows, false);
        for (int g = 0; g < groups; ++g) for (int e = starts[g]; e < starts[g + 1]; ++e) {
            owned[dest[e]] = true;
            for (int r : {0, int(L.n_embd / 2), int(L.n_embd - 1)}) {
                double want = reference(g, e, r), got = control[(size_t)dest[e] * L.n_embd + r];
                if (!std::isfinite(got)) good = false;
                err += std::abs(got - want); den += std::abs(want);
            }
        }
        for (int r = 0; r < output_rows; ++r) for (int c = 0; c < L.n_embd; ++c) {
            float v = control[(size_t)r * L.n_embd + c];
            if (owned[r] ? !std::isfinite(v) : !std::isnan(v)) good = false;
        }
        if (err > 2e-6 * std::max(1e-15, den)) good = false;
        std::printf("{\"kind\":\"correctness\",\"groups\":%d,\"entries\":%d,\"rows\":%lld,\"grid_groups\":%d,\"relative_l1\":%.9g,\"passed\":%s}\n",
                    groups, entries, (long long)L.n_embd, grid_groups, err/std::max(1e-15,den), good ? "true":"false");
        return good;
    }
    double measure(int lanes, hipStream_t s, int iterations) {
        hipGraph_t graph; hipGraphExec_t exec;
        ck(hipStreamBeginCapture(s, hipStreamCaptureModeThreadLocal));
        for (int i = 0; i < iterations; ++i) launch(lanes, i % banks, s);
        ck(hipStreamEndCapture(s, &graph)); ck(hipGraphInstantiate(&exec, graph, nullptr, nullptr, 0));
        ck(hipGraphLaunch(exec, s)); ck(hipStreamSynchronize(s));
        const long evictions_before = evicted_ms();
        hipEvent_t start, end; ck(hipEventCreate(&start)); ck(hipEventCreate(&end));
        ck(hipEventRecord(start,s)); ck(hipGraphLaunch(exec,s)); ck(hipEventRecord(end,s)); ck(hipEventSynchronize(end));
        float ms; ck(hipEventElapsedTime(&ms,start,end));
        timed_evicted_ms = evicted_ms() - evictions_before;
        ck(hipEventDestroy(start)); ck(hipEventDestroy(end)); ck(hipGraphExecDestroy(exec)); ck(hipGraphDestroy(graph));
        return ms * 1000.0 / iterations;
    }
};

int main(int argc, char** argv) {
    bool bench = argc > 1 && std::string(argv[1]) == "--bench";
    hipStream_t s; ck(hipStreamCreate(&s)); bool ok = true;
    if (argc == 6 && std::string(argv[1]) == "--counter") {
        int lanes = std::atoi(argv[2]), groups = std::atoi(argv[3]);
        int entries = std::atoi(argv[4]), banks = std::atoi(argv[5]);
        if ((lanes != 8 && lanes != 16 && lanes != 32) || groups < 1 || groups > 40 ||
                entries < 1 || entries > 4 || banks < 1 || banks > 4) return 2;
        Case c(std::vector<int>(groups, entries), 2560, groups, banks, 1100+groups+entries);
        for (int i = 0; i < 16; ++i) { c.launch(lanes, i % banks, s); ck(hipStreamSynchronize(s)); }
        std::printf("{\"kind\":\"counter_probe\",\"lanes\":%d,\"groups\":%d,\"entries\":%d,\"banks\":%d}\n", lanes, groups, entries, banks);
        ck(hipStreamDestroy(s)); return 0;
    }
    for (int rows : {31, 2560}) for (int gy : {1, 4, 15}) {
        Case c({0, 1, 3, 0, 4, 2, 0, 5, 8, 11, 1, 0}, rows, gy, 1, 600 + rows + gy);
        ok = c.check(s) && ok;
    }
    { Case c({}, 2560, 3, 1, 7); ok = c.check(s) && ok; }
    if (!ok) return 1;
    if (bench) for (int groups : {10, 20, 30, 40}) for (int entries : {1, 2, 4}) for (int banks : {1, 4}) {
        Case c(std::vector<int>(groups, entries), 2560, groups, banks, 1100+groups+entries);
        if (!c.check(s)) return 1;
        for (int trial = 0; trial < 5; ++trial) {
            const std::vector<int> order = trial % 2 ? std::vector<int>{8,16,32}:std::vector<int>{32,16,8};
            for (int lanes : order) {
                double us = c.measure(lanes,s,40);
                std::printf("{\"kind\":\"timing\",\"groups\":%d,\"entries_per_group\":%d,\"banks\":%d,\"trial\":%d,\"lanes\":%d,\"us\":%.6f,\"unique_weight_bytes\":%zu,\"timed_evicted_ms\":%ld}\n",
                            groups,entries,banks,trial,lanes,us,size_t(groups)*2560*640*24/32,c.timed_evicted_ms);
            }
        }
        std::fflush(stdout);
    }
    ck(hipStreamDestroy(s)); return 0;
}
