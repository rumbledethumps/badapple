cmake_minimum_required(VERSION 3.28)

include(${CMAKE_CURRENT_LIST_DIR}/tools/rp6502.cmake)

project(BADAPPLE C ASM)

add_executable(badapple)
rp6502_align(badapple "XRAM_.*")
rp6502_asset(badapple help src/help.txt)

# src/encode.py writes the archive of tiles.bin, frames.bin, index.bin,
# title.bin, and transport.bin.
# The build unpacks it and packages the files in the ROM.
set(BADAPPLE_ARCHIVE ${CMAKE_SOURCE_DIR}/src/badapple.tar.xz)
set(BADAPPLE_DATA ${CMAKE_CURRENT_BINARY_DIR}/badapple-data)
if(EXISTS ${BADAPPLE_ARCHIVE})
    add_custom_command(
        OUTPUT ${BADAPPLE_DATA}/tiles.bin ${BADAPPLE_DATA}/frames.bin ${BADAPPLE_DATA}/index.bin ${BADAPPLE_DATA}/title.bin ${BADAPPLE_DATA}/transport.bin
        COMMAND ${CMAKE_COMMAND} -E make_directory ${BADAPPLE_DATA}
        COMMAND ${CMAKE_COMMAND} -E chdir ${BADAPPLE_DATA} ${CMAKE_COMMAND} -E tar xf ${BADAPPLE_ARCHIVE} --touch
        DEPENDS ${BADAPPLE_ARCHIVE}
        COMMENT "Unpacking src/badapple.tar.xz"
        VERBATIM
    )
    rp6502_asset(badapple XRAM(XRAM_TILES) ${BADAPPLE_DATA}/tiles.bin)
    rp6502_asset(badapple XRAM(XRAM_TRANSPORT) ${BADAPPLE_DATA}/transport.bin)
    rp6502_asset(badapple frames ${BADAPPLE_DATA}/frames.bin)
    rp6502_asset(badapple index ${BADAPPLE_DATA}/index.bin)
    rp6502_asset(badapple title ${BADAPPLE_DATA}/title.bin)
    rp6502_test(NAME play COMMAND tests/play.txt $<TARGET_PROPERTY:badapple,RP6502_ROM>)
else()
    message(WARNING "No src/badapple.tar.xz. Run src/encode.py first.")
endif()

rp6502_executable(badapple DATA default RESET default)
# The ROM has its own title screen and play button, so the web player starts
# it at once with no overlay of its own; the browser allows sound at the
# first click on it. The footer has links to GitHub, the ROM, and the
# Picocomputer site under it.
rp6502_web(badapple CONFIG [[
    overlay: false,
    footer: 'Bad Apple!! by ZUN, Masayoshi Minoshima, nomico, Haruka, Μμ, and Anira.',
]])
target_sources(badapple PRIVATE
    src/main.c
    src/transport.c
    src/copy.s
)
# The C flags of the build reach the assembler too, which does not use them.
set_source_files_properties(src/copy.s PROPERTIES COMPILE_OPTIONS -Wno-unused-command-line-argument)
