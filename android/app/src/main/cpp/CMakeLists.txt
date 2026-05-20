cmake_minimum_required(VERSION 3.22.1)
project("zim_zstd")

include(FetchContent)
FetchContent_Declare(
    zstd
    URL https://github.com/facebook/zstd/releases/download/v1.5.6/zstd-1.5.6.tar.gz
    SOURCE_SUBDIR build/cmake
)
set(ZSTD_BUILD_PROGRAMS    OFF CACHE BOOL "" FORCE)
set(ZSTD_BUILD_TESTS       OFF CACHE BOOL "" FORCE)
set(ZSTD_BUILD_SHARED      OFF CACHE BOOL "" FORCE)
set(ZSTD_MULTITHREAD_SUPPORT OFF CACHE BOOL "" FORCE)
FetchContent_MakeAvailable(zstd)

add_library(zim_zstd SHARED zstd_jni.cpp)
target_link_libraries(zim_zstd PRIVATE libzstd_static log)
target_include_directories(zim_zstd PRIVATE ${zstd_SOURCE_DIR}/lib)
