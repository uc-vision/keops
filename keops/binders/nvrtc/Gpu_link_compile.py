import os
from ctypes import create_string_buffer, CDLL, c_int
from os import RTLD_LAZY

from keops.binders.LinkCompile import LinkCompile
from keops.config.config import (
    cuda_version,
    get_build_folder,
    jit_binary,
    cxx_compiler,
    nvrtc_flags,
    nvrtc_include,
    jit_source_file,
    cuda_available,
)
from keops.utils.misc_utils import KeOps_Error, KeOps_Message
from keops.utils.gpu_utils import get_gpu_props, cuda_include_fp16_path


class Gpu_link_compile(LinkCompile):
    source_code_extension = "cu"
    target_prefix = "cubin_" if cuda_version >= 11010 else "ptx_"

    # these were used for command line compiling mode
    # compiler = "nvcc"
    # compile_options = ["-shared", "-Xcompiler -fPIC", "-O3"]

    ngpu, gpu_props_compile_flags = get_gpu_props()

    def __init__(self):
        # checking that the system has a Gpu :
        if not (cuda_available and Gpu_link_compile.ngpu):
            KeOps_Error(
                "Trying to compile cuda code... but we detected that the system has no properly configured cuda lib."
            )

        # binary for JIT compiling.
        self.compile_jit_binary()

        LinkCompile.__init__(self)
        # these are used for JIT compiling mode
        # target_file is filename of low level code (PTX for Cuda) or binary (CUBIN for Cuda)
        # generated by the JIT compiler, e.g. ptx_7b9a611f7e
        self.target_file = os.path.join(
            get_build_folder(), self.target_prefix + self.gencode_filename
        ).encode("utf-8")

        self.my_c_dll = CDLL(jit_binary, mode=RTLD_LAZY)
        # actual dll to be called is the jit binary
        self.true_dllname = jit_binary
        # file to check for existence to detect compilation is needed
        self.file_to_check = self.target_file

    def compile_code(self):
        # method to generate the code and compile it
        # generate the code and save it in self.code, by calling get_code method from GpuReduc class :
        self.get_code()
        # write the code in the source file
        self.write_code()
        # we execute the main dll, passing the code as argument, and the name of the low level code file to save the assembly instructions
        self.my_c_dll.Compile(
            create_string_buffer(self.target_file),
            create_string_buffer(self.code.encode("utf-8")),
            c_int(self.use_half),
            c_int(self.device_id),
            create_string_buffer((cuda_include_fp16_path()+os.path.sep).encode("utf-8")),
        )
        # retreive some parameters that will be saved into info_file.
        self.tagI = self.red_formula.tagI
        self.dim = self.red_formula.dim

    @staticmethod
    def compile_jit_binary():
        # This is about the main KeOps binary (dll) that will be used to JIT compile all formulas.
        # If the dll is not present, it compiles it from source, except if check_compile is False.
        if not os.path.exists(jit_binary):
            KeOps_Message("Compiling main dll ... ", flush=True, end="")
            target_tag = (
                "CUBIN" if Gpu_link_compile.target_prefix == "cubin_" else "PTX"
            )
            nvrtcGetTARGET = "nvrtcGet" + target_tag
            nvrtcGetTARGETSize = nvrtcGetTARGET + "Size"
            arch_tag = (
                '\\"sm\\"'
                if Gpu_link_compile.target_prefix == "cubin_"
                else '\\"compute\\"'
            )
            target_type_define = f"-DnvrtcGetTARGET={nvrtcGetTARGET} -DnvrtcGetTARGETSize={nvrtcGetTARGETSize} -DARCHTAG={arch_tag}"
            jit_compile_command = f"{cxx_compiler} {nvrtc_flags} {target_type_define} {nvrtc_include} {Gpu_link_compile.gpu_props_compile_flags} {jit_source_file} -o {jit_binary}"
            os.system(jit_compile_command)
            print("OK", flush=True)
