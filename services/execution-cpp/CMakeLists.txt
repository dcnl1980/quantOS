cmake_minimum_required(VERSION 3.20)
project(quant_execution_cpp LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

add_executable(quant-execution
    src/main.cpp
    src/engine.cpp
)
target_include_directories(quant-execution PRIVATE include)
target_compile_options(quant-execution PRIVATE -O3 -Wall -Wextra -Wpedantic)

add_executable(engine-tests
    tests/engine_tests.cpp
    src/engine.cpp
)
target_include_directories(engine-tests PRIVATE include)
target_compile_options(engine-tests PRIVATE -O2 -Wall -Wextra -Wpedantic)

enable_testing()
add_test(NAME engine-tests COMMAND engine-tests)
