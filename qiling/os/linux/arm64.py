#!/usr/bin/env python3
# 
# Cross Platform and Multi Architecture Advanced Binary Emulation Framework
# Built on top of Unicorn emulator (www.unicorn-engine.org) 

import traceback

from unicorn import *
from unicorn.arm64_const import *

from qiling.loader.elf import *
from qiling.os.linux.arm64_syscall import *
from qiling.os.posix.syscall import *
from qiling.os.linux.syscall import *
from qiling.os.utils import *
from qiling.arch.filetype import *

QL_ARM64_LINUX_PREDEFINE_STACKADDRESS = 0x7ffffffde000
QL_ARM64_LINUX_PREDEFINE_STACKSIZE = 0x21000
QL_ARM64_EMU_END = 0xffffffffffffffff

def hook_syscall(ql, intno):
    syscall_num  = ql.uc.reg_read(UC_ARM64_REG_X8)
    param0 = ql.uc.reg_read(UC_ARM64_REG_X0)
    param1 = ql.uc.reg_read(UC_ARM64_REG_X1)
    param2 = ql.uc.reg_read(UC_ARM64_REG_X2)
    param3 = ql.uc.reg_read(UC_ARM64_REG_X3)
    param4 = ql.uc.reg_read(UC_ARM64_REG_X4)
    param5 = ql.uc.reg_read(UC_ARM64_REG_X5)
    pc = ql.uc.reg_read(UC_ARM64_REG_PC)

    while 1:
        LINUX_SYSCALL_FUNC = ql.dict_posix_syscall.get(syscall_num, None)
        if LINUX_SYSCALL_FUNC != None:
            LINUX_SYSCALL_FUNC_NAME = LINUX_SYSCALL_FUNC.__name__
            break
        LINUX_SYSCALL_FUNC_NAME = dict_arm64_linux_syscall.get(syscall_num, None)
        if LINUX_SYSCALL_FUNC_NAME != None:
            LINUX_SYSCALL_FUNC = eval(LINUX_SYSCALL_FUNC_NAME)
            break
        LINUX_SYSCALL_FUNC = None
        LINUX_SYSCALL_FUNC_NAME = None
        break

    if LINUX_SYSCALL_FUNC != None:
        try:
            LINUX_SYSCALL_FUNC(ql, param0, param1, param2, param3, param4, param5)
        except KeyboardInterrupt:
            raise
        except Exception as e:
            ql.nprint("[!] SYSCALL: ", LINUX_SYSCALL_FUNC_NAME)
            ql.nprint("[-] ERROR: %s" % (e))
            if ql.output in (QL_OUT_DEBUG, QL_OUT_DUMP):
                if ql.debug_stop:
                    ql.nprint("[-] Stopped due to ql.debug_stop is True")
                    ql.nprint(traceback.format_exc())
                    raise QlErrorSyscallError("[!] Syscall Implenetation Error")

    else:
        ql.nprint("[!] 0x%x: syscall number = 0x%x(%d) not implement" %(pc, syscall_num,  syscall_num))
        if ql.debug_stop:
            ql.nprint("[-] Stopped due to ql.debug_stop is True")
            ql.nprint(traceback.format_exc())
            raise QlErrorSyscallNotFound("[!] Syscall Not Found")


def ql_arm64_enable_vfp(uc):
    ARM64FP = uc.reg_read(UC_ARM64_REG_CPACR_EL1)
    ARM64FP |= 0x300000
    uc.reg_write(UC_ARM64_REG_CPACR_EL1, ARM64FP)


def loader_file(ql):
    uc = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
    ql.uc = uc
    if (ql.stack_address == 0):
        ql.stack_address = QL_ARM64_LINUX_PREDEFINE_STACKADDRESS
    if (ql.stack_size == 0):  
        ql.stack_size = QL_ARM64_LINUX_PREDEFINE_STACKSIZE
    ql.uc.mem_map(ql.stack_address, ql.stack_size)
    loader = ELFLoader(ql.path, ql)
    if loader.load_with_ld(ql, ql.stack_address + ql.stack_size, argv = ql.argv,  env = ql.env):
        raise QlErrorFileType("Unsupported FileType")
    ql.stack_address = (int(ql.new_stack))


def loader_shellcode(ql):
    uc = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
    ql.uc = uc

    if (ql.stack_address == 0):
        ql.stack_address = 0x1000000
    if (ql.stack_size == 0): 
        ql.stack_size = 2 * 1024 * 1024
    ql.uc.mem_map(ql.stack_address, ql.stack_size)
    ql.stack_address =  ql.stack_address  + 0x200000 - 0x1000    
    ql.uc.mem_write(ql.stack_address, ql.shellcoder) 

def runner(ql):
    ql.uc.reg_write(UC_ARM64_REG_SP, ql.stack_address)
    ql_setup(ql)
    ql.hook_intr(hook_syscall)
    ql_arm64_enable_vfp(ql.uc)
    if (ql.until_addr == 0):
        ql.until_addr = QL_ARM64_EMU_END
    try:
        if ql.shellcoder:
            ql.uc.emu_start(ql.stack_address, (ql.stack_address + len(ql.shellcoder)))
        else:    
            ql.uc.emu_start(ql.entry_point, ql.until_addr, ql.timeout)
    except UcError as e:
        if ql.output in (QL_OUT_DEBUG, QL_OUT_DUMP):
            ql.nprint("[+] PC= " + hex(ql.pc))
            ql.show_map_info()
            buf = ql.uc.mem_read(ql.pc, 8)
            ql.nprint("[+] ", [hex(_) for _ in buf])
            ql_hook_code_disasm(ql, ql.pc, 64)
        raise QlErrorExecutionStop('[!] Emulation Stopped due to %s' %(e))

    if ql.internal_exception != None:
        raise ql.internal_exception
