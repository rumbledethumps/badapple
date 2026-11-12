; The delta decoder's inner loops, for main.c.
;
; decode_runs() applies runs of a delta block from the ring, through the
; XRAM portals: RW1 reads the ring at ADDR1, RW0 writes the maps at ADDR0.
; Before the call, main.c sets STEP0 and STEP1 to 1, ADDR1 to the next run
; in the ring, dec_map to the XRAM address of the maps being decoded, and
; dec_limit to the first page of the ring where a run might reach its end.
; A run is a 2-byte map offset, a count of 1 to 255, and that many tile IDs;
; FF FF ends the block. ADDR1 is left after the last byte read, so main.c
; reads the new position back from it. decode_runs() returns:
;   0  after about 256 bytes, so the main loop can check VSYNC,
;   1  at the end of the block, after its FF FF,
;   2  at dec_limit, where a run might wrap: main.c applies the next run
;      itself.
;
; copy_run(count) copies count bytes, 1 to 255, from ADDR1 to ADDR0.
;
; Eight bytes a pass in the copy, about 8.6 cycles a byte. The counters
; are in zero page.

RW0 = $ffe4
ADDR0 = $ffe6
RW1 = $ffe8
ADDR1 = $ffea

.macro copy_y
    tya
    and #7
    beq 2f
    tax
1:
    lda RW1
    sta RW0
    dex
    bne 1b
2:
    tya
    lsr
    lsr
    lsr
    beq 4f
    tax
3:
    .rept 8
    lda RW1
    sta RW0
    .endr
    dex
    bne 3b
4:
.endm

.section .text.copy_run,"ax",@progbits
.globl copy_run
copy_run:
    tay
    copy_y
    rts

.section .text.decode_runs,"ax",@progbits
.globl decode_runs
decode_runs:
    lda #0
    sta mos8(budget)
.Lrun:
    lda ADDR1+1
    cmp mos8(dec_limit)
    bcc .Lroom
    lda #2
    rts
.Lroom:
    ldx RW1                 ; offset, low byte
    ldy RW1                 ; offset, high byte
    cpy #$ff
    bne .Lstart
    cpx #$ff
    bne .Lstart
    lda #1                  ; the end of the block
    rts
.Lstart:
    clc                     ; ADDR0 = dec_map + offset
    txa
    adc mos8(dec_map)
    sta ADDR0
    tya
    adc mos8(dec_map+1)
    sta ADDR0+1
    ldy RW1                 ; count
    sty mos8(count)
    copy_y
    clc                     ; stop after about 256 bytes
    lda mos8(budget)
    adc mos8(count)
    sta mos8(budget)
    bcs .Lpause
    jmp .Lrun
.Lpause:
    lda #0
    rts

.section .zp.bss.decode_runs,"aw",@nobits
.globl dec_map
.globl dec_limit
dec_map:
    .zero 2
dec_limit:
    .zero 1
budget:
    .zero 1
count:
    .zero 1
