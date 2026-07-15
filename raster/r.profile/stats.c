/*
 * Copyright (C) 2026 by the GRASS Development Team
 *
 * This Program is free software under the GPL (>=v2)
 * Read the file COPYING coming with GRASS for details
 *
 */

#include <math.h>
#include <stdio.h>
#include <stdlib.h>

#include <grass/gis.h>
#include <grass/gjson.h>

#include "local_proto.h"

void stats_add_value(struct ProfileStats *stats, double value)
{
    if (stats->n == stats->n_alloc) {
        stats->n_alloc = stats->n_alloc ? 2 * stats->n_alloc : 1024;
        stats->values =
            G_realloc(stats->values, stats->n_alloc * sizeof(double));
    }
    stats->values[stats->n++] = value;
}

void stats_add_null(struct ProfileStats *stats)
{
    stats->nulls++;
}

static int compare_double(const void *a, const void *b)
{
    double diff = *(const double *)a - *(const double *)b;

    return (diff > 0) - (diff < 0);
}

/* Compute and output statistics of the collected profile values.
 *
 * Sorts stats->values in place to obtain the median. The variance and
 * the standard deviation are the population (not sample) statistics and
 * coeff_var is the ratio stddev/mean, matching the statistics previously
 * computed by the wxGUI profile tool with numpy.
 *
 * For JSON, the statistics are added as a "statistics" member of the
 * given root object; for plain format, they are printed to fp as
 * key=value lines. When there are no non-null values, all statistics
 * except the counts are null in JSON and omitted in plain format;
 * coeff_var additionally requires a non-zero mean. */
void print_stats(struct ProfileStats *stats, FILE *fp, enum OutputFormat format,
                 G_JSON_Object *root)
{
    double min = 0, max = 0, sum = 0, mean = 0, variance = 0, median = 0;
    size_t i;

    if (stats->n > 0) {
        qsort(stats->values, stats->n, sizeof(double), compare_double);
        min = stats->values[0];
        max = stats->values[stats->n - 1];
        for (i = 0; i < stats->n; i++)
            sum += stats->values[i];
        mean = sum / stats->n;
        for (i = 0; i < stats->n; i++)
            variance += (stats->values[i] - mean) * (stats->values[i] - mean);
        variance /= stats->n;
        if (stats->n % 2)
            median = stats->values[stats->n / 2];
        else
            median = (stats->values[stats->n / 2 - 1] +
                      stats->values[stats->n / 2]) /
                     2;
    }

    if (format == JSON) {
        G_JSON_Value *stats_value = G_json_value_init_object();
        G_JSON_Object *object = G_json_object(stats_value);

        G_json_object_set_number(object, "n", (double)stats->n);
        G_json_object_set_number(object, "nulls", (double)stats->nulls);
        if (stats->n > 0) {
            G_json_object_set_number(object, "min", min);
            G_json_object_set_number(object, "max", max);
            G_json_object_set_number(object, "range", max - min);
            G_json_object_set_number(object, "mean", mean);
            G_json_object_set_number(object, "stddev", sqrt(variance));
            G_json_object_set_number(object, "variance", variance);
            if (mean != 0)
                G_json_object_set_number(object, "coeff_var",
                                         sqrt(variance) / mean);
            else
                G_json_object_set_null(object, "coeff_var");
            G_json_object_set_number(object, "sum", sum);
            G_json_object_set_number(object, "median", median);
        }
        else {
            G_json_object_set_null(object, "min");
            G_json_object_set_null(object, "max");
            G_json_object_set_null(object, "range");
            G_json_object_set_null(object, "mean");
            G_json_object_set_null(object, "stddev");
            G_json_object_set_null(object, "variance");
            G_json_object_set_null(object, "coeff_var");
            G_json_object_set_null(object, "sum");
            G_json_object_set_null(object, "median");
        }
        G_json_object_set_value(root, "statistics", stats_value);
    }
    else {
        fprintf(fp, "n=%lu\n", (unsigned long)stats->n);
        fprintf(fp, "nulls=%lu\n", (unsigned long)stats->nulls);
        if (stats->n > 0) {
            fprintf(fp, "min=%f\n", min);
            fprintf(fp, "max=%f\n", max);
            fprintf(fp, "range=%f\n", max - min);
            fprintf(fp, "mean=%f\n", mean);
            fprintf(fp, "stddev=%f\n", sqrt(variance));
            fprintf(fp, "variance=%f\n", variance);
            if (mean != 0)
                fprintf(fp, "coeff_var=%f\n", sqrt(variance) / mean);
            fprintf(fp, "sum=%f\n", sum);
            fprintf(fp, "median=%f\n", median);
        }
    }
}
