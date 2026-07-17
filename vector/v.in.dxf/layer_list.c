#include <string.h>

#include <grass/gjson.h>

#include "global.h"

static int num_layers = 0;
static char **layers = NULL;

void add_layer_to_list(const char *layer, int print)
{
    if (is_layer_in_list(layer))
        return;

    layers = (char **)G_realloc(layers, (num_layers + 2) * sizeof(char *));
    layers[num_layers] = G_store(layer);
    G_str_to_lower(layers[num_layers]);
    /* JSON output is printed at once by print_layer_list_json() when the
     * whole file has been scanned */
    if (print && !format_json) {
        fprintf(stdout, _("Layer %d: %s\n"), num_layers + 1,
                layers[num_layers]);
        fflush(stdout);
    }
    num_layers++;
    layers[num_layers] = NULL;

    return;
}

int is_layer_in_list(const char *layer)
{
    char **p;

    if (!layers)
        return 0;

    p = layers;
    while (*p && G_strcasecmp(layer, *p) != 0)
        p++;

    return *p != NULL;
}

void print_layer_list_json(void)
{
    int i;
    char *serialized;
    G_JSON_Value *root_value, *layer_value;
    G_JSON_Array *root_array;
    G_JSON_Object *layer_object;

    root_value = G_json_value_init_array();
    if (!root_value)
        G_fatal_error(_("Failed to initialize JSON array. Out of memory?"));
    root_array = G_json_array(root_value);

    for (i = 0; i < num_layers; i++) {
        layer_value = G_json_value_init_object();
        if (!layer_value)
            G_fatal_error(
                _("Failed to initialize JSON object. Out of memory?"));
        layer_object = G_json_object(layer_value);
        G_json_object_set_number(layer_object, "index", i + 1);
        G_json_object_set_string(layer_object, "name", layers[i]);
        G_json_array_append_value(root_array, layer_value);
    }

    serialized = G_json_serialize_to_string_pretty(root_value);
    if (!serialized)
        G_fatal_error(_("Failed to serialize JSON to pretty format."));
    puts(serialized);
    fflush(stdout);

    G_json_free_serialized_string(serialized);
    G_json_value_free(root_value);
}

void init_list(void)
{
    char **p;

    if (!layers)
        return;

    p = layers;
    while (*p) {
        G_free(*p);
        p++;
    }

    G_free(layers);
    layers = NULL;

    return;
}
