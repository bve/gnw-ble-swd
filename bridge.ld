/* S140 6.1.1 application, with an isolated SPIM3 transmit RAM slave. */
SEARCH_DIR(.)
GROUP(-lgcc -lc -lnosys)

MEMORY
{
    FLASH (rx) : ORIGIN = 0x26000, LENGTH = 0xED000 - 0x26000
    RAM (rwx) : ORIGIN = 0x20006000, LENGTH = 0x20040000 - 0x20006000
}

SECTIONS
{
    .svc_data : ALIGN(4)
    {
        PROVIDE(__start_svc_data = .);
        KEEP(*(.svc_data))
        PROVIDE(__stop_svc_data = .);
    } > RAM
    .fs_data : ALIGN(4)
    {
        PROVIDE(__start_fs_data = .);
        KEEP(*(.fs_data))
        PROVIDE(__stop_fs_data = .);
    } > RAM
} INSERT AFTER .data;

SECTIONS
{
    /* Nordic anomaly 198: no CPU access to the SPIM3 TX RAM AHB slave
       while DMA is active. Reserve the entire aligned 8 KiB slave. */
    .swd_dma ALIGN(8192) (NOLOAD) :
    {
        __swd_dma_start__ = .;
        KEEP(*(.swd_dma))
        . = __swd_dma_start__ + 8192;
        __swd_dma_end__ = .;
    } > RAM
    ASSERT(__swd_dma_end__ <= 0x20010000, "SPIM3 TX needs an exclusive 8 KiB RAM slave below 0x20010000")
} INSERT BEFORE .bss;

INCLUDE "nrf52_common.ld"
