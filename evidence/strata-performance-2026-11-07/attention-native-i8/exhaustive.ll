; ModuleID = 'tests/hip/pa_native_i8.cpp'
source_filename = "tests/hip/pa_native_i8.cpp"
target datalayout = "e-m:e-p:64:64-p1:64:64-p2:32:32-p3:32:32-p4:64:64-p5:32:32-p6:32:32-p7:160:256:256:32-p8:128:128:128:48-p9:192:256:256:32-i64:64-v16:16-v24:32-v32:32-v48:64-v96:128-v192:256-v256:256-v512:512-v1024:1024-v2048:2048-n32:64-S32-A5-G1-ni:7:8:9"
target triple = "amdgcn-amd-amdhsa"

@__hip_cuid_b62499609a18c155 = addrspace(1) global i8 0
@llvm.compiler.used = appending addrspace(1) global [1 x ptr] [ptr addrspacecast (ptr addrspace(1) @__hip_cuid_b62499609a18c155 to ptr)], section "llvm.metadata"

; Function Attrs: convergent mustprogress norecurse nounwind memory(argmem: write)
define protected amdgpu_kernel void @_Z12decode_pairsPt(ptr addrspace(1) noundef writeonly captures(none) %0) local_unnamed_addr #0 {
  %2 = tail call noundef i32 @llvm.amdgcn.workgroup.id.x()
  %3 = tail call noundef dereferenceable(256) ptr addrspace(4) @llvm.amdgcn.implicitarg.ptr()
  %4 = getelementptr inbounds nuw i8, ptr addrspace(4) %3, i64 12
  %5 = load i16, ptr addrspace(4) %4, align 4, !tbaa !13, !range !15
  %6 = zext nneg i16 %5 to i32
  %7 = mul i32 %2, %6
  %8 = tail call noundef range(i32 0, 1024) i32 @llvm.amdgcn.workitem.id.x()
  %9 = add i32 %7, %8
  %10 = icmp ugt i32 %9, 65535
  br i1 %10, label %101, label %11

11:                                               ; preds = %1
  %12 = shl nuw i32 %9, 16
  %13 = or disjoint i32 %12, %9
  %14 = xor i32 %13, -1520828416
  %15 = add nuw nsw i32 %9, 997
  %16 = and i32 %15, 65535
  %17 = shl nuw i32 %9, 16
  %18 = or disjoint i32 %17, %16
  %19 = xor i32 %18, -1504378880
  %20 = add nuw nsw i32 %9, 1994
  %21 = and i32 %20, 65535
  %22 = shl nuw i32 %9, 16
  %23 = or disjoint i32 %22, %21
  %24 = xor i32 %23, -1487929344
  %25 = add nuw nsw i32 %9, 2991
  %26 = and i32 %25, 65535
  %27 = shl nuw i32 %9, 16
  %28 = or disjoint i32 %27, %26
  %29 = xor i32 %28, -1471479808
  %30 = shl i32 %9, 24
  %31 = ashr exact i32 %30, 24
  %32 = tail call i32 asm "v_cvt_f16_i16_e64 $0.l, $1.l", "=v,v"(i32 %31) #2, !srcloc !16
  %33 = trunc i32 %32 to i16
  %34 = shl nuw i32 %9, 16
  %35 = ashr i32 %34, 24
  %36 = tail call i32 asm "v_cvt_f16_i16_e64 $0.l, $1.l", "=v,v"(i32 %35) #2, !srcloc !16
  %37 = shl i32 %14, 8
  %38 = ashr i32 %37, 24
  %39 = tail call i32 asm "v_cvt_f16_i16_e64 $0.l, $1.l", "=v,v"(i32 %38) #2, !srcloc !16
  %40 = ashr i32 %14, 24
  %41 = tail call i32 asm "v_cvt_f16_i16_e64 $0.l, $1.l", "=v,v"(i32 %40) #2, !srcloc !16
  %42 = shl i32 %15, 24
  %43 = ashr exact i32 %42, 24
  %44 = tail call i32 asm "v_cvt_f16_i16_e64 $0.l, $1.l", "=v,v"(i32 %43) #2, !srcloc !16
  %45 = shl i32 %15, 16
  %46 = ashr i32 %45, 24
  %47 = tail call i32 asm "v_cvt_f16_i16_e64 $0.l, $1.l", "=v,v"(i32 %46) #2, !srcloc !16
  %48 = shl i32 %19, 8
  %49 = ashr i32 %48, 24
  %50 = tail call i32 asm "v_cvt_f16_i16_e64 $0.l, $1.l", "=v,v"(i32 %49) #2, !srcloc !16
  %51 = ashr i32 %19, 24
  %52 = tail call i32 asm "v_cvt_f16_i16_e64 $0.l, $1.l", "=v,v"(i32 %51) #2, !srcloc !16
  %53 = shl i32 %20, 24
  %54 = ashr exact i32 %53, 24
  %55 = tail call i32 asm "v_cvt_f16_i16_e64 $0.l, $1.l", "=v,v"(i32 %54) #2, !srcloc !16
  %56 = shl i32 %20, 16
  %57 = ashr i32 %56, 24
  %58 = tail call i32 asm "v_cvt_f16_i16_e64 $0.l, $1.l", "=v,v"(i32 %57) #2, !srcloc !16
  %59 = shl i32 %24, 8
  %60 = ashr i32 %59, 24
  %61 = tail call i32 asm "v_cvt_f16_i16_e64 $0.l, $1.l", "=v,v"(i32 %60) #2, !srcloc !16
  %62 = ashr i32 %24, 24
  %63 = tail call i32 asm "v_cvt_f16_i16_e64 $0.l, $1.l", "=v,v"(i32 %62) #2, !srcloc !16
  %64 = shl i32 %25, 24
  %65 = ashr exact i32 %64, 24
  %66 = tail call i32 asm "v_cvt_f16_i16_e64 $0.l, $1.l", "=v,v"(i32 %65) #2, !srcloc !16
  %67 = shl i32 %25, 16
  %68 = ashr i32 %67, 24
  %69 = tail call i32 asm "v_cvt_f16_i16_e64 $0.l, $1.l", "=v,v"(i32 %68) #2, !srcloc !16
  %70 = shl i32 %29, 8
  %71 = ashr i32 %70, 24
  %72 = tail call i32 asm "v_cvt_f16_i16_e64 $0.l, $1.l", "=v,v"(i32 %71) #2, !srcloc !16
  %73 = ashr i32 %29, 24
  %74 = tail call i32 asm "v_cvt_f16_i16_e64 $0.l, $1.l", "=v,v"(i32 %73) #2, !srcloc !16
  %75 = shl nuw nsw i32 %9, 4
  %76 = zext nneg i32 %75 to i64
  %77 = getelementptr inbounds nuw [2 x i8], ptr addrspace(1) %0, i64 %76
  %78 = insertelement <2 x i16> poison, i16 %33, i64 0
  %79 = shufflevector <2 x i16> %78, <2 x i16> poison, <2 x i32> zeroinitializer
  store <2 x i16> %79, ptr addrspace(1) %77, align 2, !tbaa !17
  %80 = zext nneg i32 %75 to i64
  %81 = getelementptr inbounds nuw [2 x i8], ptr addrspace(1) %0, i64 %80
  %82 = getelementptr inbounds nuw i8, ptr addrspace(1) %81, i64 4
  store <2 x i16> %79, ptr addrspace(1) %82, align 2, !tbaa !17
  %83 = zext nneg i32 %75 to i64
  %84 = getelementptr inbounds nuw [2 x i8], ptr addrspace(1) %0, i64 %83
  %85 = getelementptr inbounds nuw i8, ptr addrspace(1) %84, i64 8
  store <2 x i16> %79, ptr addrspace(1) %85, align 2, !tbaa !17
  %86 = zext nneg i32 %75 to i64
  %87 = getelementptr inbounds nuw [2 x i8], ptr addrspace(1) %0, i64 %86
  %88 = getelementptr inbounds nuw i8, ptr addrspace(1) %87, i64 12
  store <2 x i16> %79, ptr addrspace(1) %88, align 2, !tbaa !17
  %89 = zext nneg i32 %75 to i64
  %90 = getelementptr inbounds nuw [2 x i8], ptr addrspace(1) %0, i64 %89
  %91 = getelementptr inbounds nuw i8, ptr addrspace(1) %90, i64 16
  store <2 x i16> %79, ptr addrspace(1) %91, align 2, !tbaa !17
  %92 = zext nneg i32 %75 to i64
  %93 = getelementptr inbounds nuw [2 x i8], ptr addrspace(1) %0, i64 %92
  %94 = getelementptr inbounds nuw i8, ptr addrspace(1) %93, i64 20
  store <2 x i16> %79, ptr addrspace(1) %94, align 2, !tbaa !17
  %95 = zext nneg i32 %75 to i64
  %96 = getelementptr inbounds nuw [2 x i8], ptr addrspace(1) %0, i64 %95
  %97 = getelementptr inbounds nuw i8, ptr addrspace(1) %96, i64 24
  store <2 x i16> %79, ptr addrspace(1) %97, align 2, !tbaa !17
  %98 = zext nneg i32 %75 to i64
  %99 = getelementptr inbounds nuw [2 x i8], ptr addrspace(1) %0, i64 %98
  %100 = getelementptr inbounds nuw i8, ptr addrspace(1) %99, i64 28
  store <2 x i16> %79, ptr addrspace(1) %100, align 2, !tbaa !17
  br label %101

101:                                              ; preds = %11, %1
  ret void
}

; Function Attrs: mustprogress nocallback nofree nosync nounwind speculatable willreturn memory(none)
declare noundef range(i32 0, 1024) i32 @llvm.amdgcn.workitem.id.x() #1

; Function Attrs: mustprogress nocallback nofree nosync nounwind speculatable willreturn memory(none)
declare noundef align 4 ptr addrspace(4) @llvm.amdgcn.implicitarg.ptr() #1

; Function Attrs: mustprogress nocallback nofree nosync nounwind speculatable willreturn memory(none)
declare noundef i32 @llvm.amdgcn.workgroup.id.x() #1

attributes #0 = { convergent mustprogress norecurse nounwind memory(argmem: write) "amdgpu-flat-work-group-size"="1,1024" "amdgpu-no-cluster-id-x" "amdgpu-no-cluster-id-y" "amdgpu-no-cluster-id-z" "amdgpu-no-completion-action" "amdgpu-no-default-queue" "amdgpu-no-dispatch-id" "amdgpu-no-dispatch-ptr" "amdgpu-no-flat-scratch-init" "amdgpu-no-heap-ptr" "amdgpu-no-hostcall-ptr" "amdgpu-no-lds-kernel-id" "amdgpu-no-multigrid-sync-arg" "amdgpu-no-queue-ptr" "amdgpu-no-workgroup-id-x" "amdgpu-no-workgroup-id-y" "amdgpu-no-workgroup-id-z" "amdgpu-no-workitem-id-x" "amdgpu-no-workitem-id-y" "amdgpu-no-workitem-id-z" "amdgpu-no-wwm" "no-trapping-math"="true" "stack-protector-buffer-size"="8" "target-cpu"="gfx1151" "uniform-work-group-size" }
attributes #1 = { mustprogress nocallback nofree nosync nounwind speculatable willreturn memory(none) }
attributes #2 = { convergent nounwind memory(none) }

!llvm.module.flags = !{!0, !1, !2}
!llvm.ident = !{!3}
!llvm.errno.tbaa = !{!4, !8}
!opencl.ocl.version = !{!12}

!0 = !{i32 1, !"amdhsa_code_object_version", i32 600}
!1 = !{i32 1, !"amdgpu_printf_kind", !"hostcall"}
!2 = !{i32 8, !"PIC Level", i32 2}
!3 = !{!"AMD clang version 23.0.0git (https://github.com/ROCm/llvm-project.git f30ae3e6b680ad23dcf522e668c6d4c5c90838d0+PATCHED:440716f8b87be9d8e20ed910e10e5b6d14d57cf6)"}
!4 = !{!5, !5, i64 0}
!5 = !{!"int", !6, i64 0}
!6 = !{!"omnipotent char", !7, i64 0}
!7 = !{!"Simple C++ TBAA"}
!8 = !{!9, !9, i64 0}
!9 = !{!"int", !10, i64 0}
!10 = !{!"omnipotent char", !11, i64 0}
!11 = !{!"Simple C/C++ TBAA"}
!12 = !{i32 2, i32 0}
!13 = !{!14, !14, i64 0}
!14 = !{!"short", !10, i64 0}
!15 = !{i16 1, i16 1025}
!16 = !{i64 6592409}
!17 = !{!18, !18, i64 0}
!18 = !{!"short", !6, i64 0}
