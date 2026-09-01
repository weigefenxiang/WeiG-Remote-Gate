#ifndef REMOTE_GATE_VERSION
#define REMOTE_GATE_VERSION "dev"
#endif

#define REMOTE_GATE_MAPPER_API 1
#define main remote_gate_mapper_main
#include "remote-gate-mapper.c"
#undef main

int main(int argc, char **argv) {
    if (argc == 2 && strcmp(argv[1], "--version") == 0) {
        printf("remote-gate-mapper %s api=%d\n", REMOTE_GATE_VERSION, REMOTE_GATE_MAPPER_API);
        return 0;
    }
    return remote_gate_mapper_main(argc, argv);
}
