#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <grass/gjson.h>
#include <grass/gis.h>
#include <grass/raster.h>

enum OutputFormat { PLAIN, CSV, JSON };

/* Accumulator for the -s statistics output. All sampled non-null values
   are kept in memory so that the median can be computed. */
struct ProfileStats {
    size_t n;       /* number of non-null values */
    size_t nulls;   /* number of null or out-of-region values */
    size_t n_alloc; /* allocated length of values */
    double *values;
};

/* main.c */
int do_profile(double, double, double, double, int, double, int, int, FILE *,
               char *, const char *, double, enum OutputFormat, G_JSON_Array *,
               ColorFormat);

/* read_rast.c */
int read_rast(double, double, double, int, int, RASTER_MAP_TYPE, FILE *, char *,
              enum OutputFormat, G_JSON_Array *, ColorFormat);

/* input.c */
int input(char *, char *, char *, char *, char *, FILE *);

/* stats.c */
void stats_add_value(struct ProfileStats *, double);
void stats_add_null(struct ProfileStats *);
void print_stats(struct ProfileStats *, FILE *, enum OutputFormat,
                 G_JSON_Object *);

extern int clr;
extern struct Colors colors;
extern char *fs;
extern struct ProfileStats *stats;
