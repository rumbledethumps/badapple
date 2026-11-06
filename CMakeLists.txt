cmake_minimum_required(VERSION 3.28)

include(${CMAKE_CURRENT_LIST_DIR}/tools/rp6502.cmake)

project(BADAPPLE C)

# A test build reads frames.bin from the current directory, for a ROM small
# enough to upload to a machine quickly.
option(BADAPPLE_TEST "Read frames.bin from the current directory instead of the ROM" OFF)

add_executable(badapple)
rp6502_align(badapple "XRAM_.*")
rp6502_asset(badapple help src/help.txt)

# src/encode.py writes the archive of tiles.bin and frames.bin.
# The build unpacks it and packages the files in the ROM.
set(BADAPPLE_ARCHIVE ${CMAKE_SOURCE_DIR}/src/badapple.tar.xz)
set(BADAPPLE_DATA ${CMAKE_CURRENT_BINARY_DIR}/badapple-data)
if(EXISTS ${BADAPPLE_ARCHIVE})
    add_custom_command(
        OUTPUT ${BADAPPLE_DATA}/tiles.bin ${BADAPPLE_DATA}/frames.bin
        COMMAND ${CMAKE_COMMAND} -E make_directory ${BADAPPLE_DATA}
        COMMAND ${CMAKE_COMMAND} -E chdir ${BADAPPLE_DATA} ${CMAKE_COMMAND} -E tar xf ${BADAPPLE_ARCHIVE} --touch
        DEPENDS ${BADAPPLE_ARCHIVE}
        COMMENT "Unpacking src/badapple.tar.xz"
        VERBATIM
    )
    rp6502_asset(badapple XRAM(XRAM_TILES) ${BADAPPLE_DATA}/tiles.bin)
    if(BADAPPLE_TEST)
        target_compile_definitions(badapple PRIVATE BADAPPLE_TEST)
    else()
        rp6502_asset(badapple frames ${BADAPPLE_DATA}/frames.bin)
    endif()
    rp6502_test(NAME play COMMAND tests/play.txt $<TARGET_PROPERTY:badapple,RP6502_ROM>)
else()
    message(WARNING "No src/badapple.tar.xz. Run src/encode.py first.")
endif()

rp6502_executable(badapple DATA default RESET default)
# The web player shows the footer with links to GitHub, the ROM, and the
# Picocomputer site under it.
rp6502_web(badapple CONFIG [[
    footer: 'Bad Apple!! by ZUN, arranged by Masayoshi Minoshima, sung by nomico (Alstroemeria Records). Shadow art by Anira and team, from the storyboard by Μμ.',
]])
target_sources(badapple PRIVATE
    src/main.c
)
