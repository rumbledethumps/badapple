cmake_minimum_required(VERSION 3.28)

include(${CMAKE_CURRENT_LIST_DIR}/tools/rp6502.cmake)

project(BADAPPLE C CXX ASM)

# encoder/encode.py writes tiles.bin and video.bin here.
set(BADAPPLE_DATA ${CMAKE_SOURCE_DIR}/data/encoded CACHE PATH "Encoded Bad Apple!! data")

add_executable(badapple)
rp6502_align(badapple "XRAM_.*")
rp6502_asset(badapple help src/help.txt)
if(EXISTS ${BADAPPLE_DATA}/tiles.bin AND EXISTS ${BADAPPLE_DATA}/video.bin)
    rp6502_asset(badapple XRAM(XRAM_TILES) ${BADAPPLE_DATA}/tiles.bin)
    rp6502_asset(badapple video ${BADAPPLE_DATA}/video.bin)
    rp6502_test(NAME play COMMAND tests/play.txt $<TARGET_PROPERTY:badapple,RP6502_ROM>)
else()
    message(WARNING "No encoded video in ${BADAPPLE_DATA}. Run encoder/encode.py first.")
endif()
rp6502_executable(badapple DATA default RESET default)
rp6502_web(badapple)
target_sources(badapple PRIVATE
    src/main.c
)
