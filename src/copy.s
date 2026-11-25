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
; clear_groups(count) writes count groups of 8 zeros, 1 to 255, at ADDR0.
;
; decode_pairs(count) decodes count pairs of 4-bit DPCM, 1 to 255, from
; RW1 at ADDR1 to 16-bit stereo samples at RW0, ADDR0. A byte holds the
; left code in its high 4 bits and the right in its low 4, and each code
; adds a delta to the channel's last sample. The deltas, at the volume, are
; in dtab, which main.c fills: for each scale k of 16, four pages indexed by
; the whole byte, dtab[k] and dtab[16 + k] the low and high bytes of the
; left delta, dtab[32 + k] and dtab[48 + k] the right's. dec_sl and dec_sr
; are the block's scales; the call writes their pages into the loop's
; loads. The last samples live in the operands of the loop's adds: main.c
; sets them through acc_ll, acc_lh, acc_rl, and acc_rh. About 69 cycles a
; pair.

; fill_scale(k) fills scale k's four pages of dtab from vlo and vhi, the
; low and high bytes of its 16 deltas, which main.c sets: in the left
; pages, byte b holds code b >> 4's delta, in the right pages code b & 15's.
; The call writes the pages into the stores, which are unrolled, so a byte
; takes 5 cycles: about 6,000 a scale.

; Eight bytes a pass in the copy, about 8.6 cycles a byte. The counters
; are in RAM: the compiler's own variables fill zero page.

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

.section .text.clear_groups,"ax",@progbits
.globl clear_groups
clear_groups:
    tax
    lda #0
1:
    .rept 8
    sta RW0
    .endr
    dex
    bne 1b
    rts

; In .data, not .text, because the loop changes its own operands.
.section .data.decode_pairs,"aw",@progbits
.macro channel load_lo, add_lo, load_hi, add_hi
    clc
\load_lo:
    lda dtab,y
\add_lo:
    adc #0
    sta \add_lo+1
    sta RW0
\load_hi:
    lda dtab,y
\add_hi:
    adc #0
    sta \add_hi+1
    sta RW0
.endm
.globl decode_pairs
.globl acc_ll
.globl acc_lh
.globl acc_rl
.globl acc_rh
decode_pairs:
    tax
    clc
    lda dec_sl
    adc #>dtab
    sta .Lll+2
    adc #16
    sta .Llh+2
    lda dec_sr
    adc #>(dtab + 32 * 256)
    sta .Lrl+2
    adc #16
    sta .Lrh+2
1:
    ldy RW1
    channel .Lll, .Lal, .Llh, .Lah
    channel .Lrl, .Lar, .Lrh, .Larh
    dex
    bne 1b
    rts
acc_ll = .Lal + 1
acc_lh = .Lah + 1
acc_rl = .Lar + 1
acc_rh = .Larh + 1

; In .data, not .text, because the call writes its own operands.
.section .data.fill_scale,"aw",@progbits
.globl fill_scale
.globl vlo
.globl vhi
fill_scale:
    clc
    adc #>dtab
.irp i, 0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15
    sta .Lsl\i+2
.endr
    adc #16
.irp i, 0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15
    sta .Lsh\i+2
.endr
    adc #16
.irp i, 0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15
    sta .Lsr\i+2
.endr
    adc #16
.irp i, 0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15
    sta .Lsq\i+2
.endr
    ldx #15
1:
    txa                     ; y = 16 * code, the code's run in the left pages
    asl
    asl
    asl
    asl
    tay
    lda vlo,x
.irp i, 0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15
.Lsl\i:
    sta dtab+\i,y
.endr
.irp i, 0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15
.Lsr\i:
    sta dtab+16*\i,x
.endr
    lda vhi,x
.irp i, 0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15
.Lsh\i:
    sta dtab+\i,y
.endr
.irp i, 0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15
.Lsq\i:
    sta dtab+16*\i,x
.endr
    dex
    bmi 2f
    jmp 1b
2:
    rts

.section .text.decode_runs,"ax",@progbits
.globl decode_runs
decode_runs:
    lda #0
    sta budget
.Lrun:
    lda ADDR1+1
    cmp dec_limit
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
    stx ADDR0               ; the run's XRAM address, as the stream gives it
    sty ADDR0+1
    ldy RW1                 ; count
    sty count
    copy_y
    clc                     ; stop after about 256 bytes
    lda budget
    adc count
    sta budget
    bcs .Lpause
    jmp .Lrun
.Lpause:
    lda #0
    rts

.section .bss.decode_runs,"aw",@nobits
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

.section .bss.decode_pairs,"aw",@nobits
.globl dec_sl
.globl dec_sr
dec_sl:
    .zero 1
dec_sr:
    .zero 1
vlo:
    .zero 16
vhi:
    .zero 16

; Page-aligned, so the indexed loads never cross a page.
.section .bss.dtab,"aw",@nobits
.balign 256
.globl dtab
dtab:
    .zero 64 * 256
