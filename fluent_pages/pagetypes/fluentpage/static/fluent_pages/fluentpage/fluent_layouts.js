/**
 * This file deals with the high level layout switching / fetching layout info.
 * When a new layout is fetched, it is passed to the fluent_contents module to rebuild the tabs.
 */
var fluent_layouts = {
    'ct_id': null,
};

(function($)
{
  var app_root = location.href.indexOf('/fluent_pages/') + 14;
  var ajax_root = location.href.substring(0, location.href.indexOf('/', app_root) + 1);
  var initial_layout_id = null;

  $.fn.ready( onReady );



  /**
   * Initialize this component,
   * bind events and select the first option if there is only one.
   */
  function onReady()
  {
    var layout_selector = $("#id_layout");
    fluent_layouts._select_single_option( layout_selector );
    layout_selector.change( fluent_layouts.onLayoutChange );
    fluent_contents.layout.onInit( fluent_layouts.fetch_layout_on_refresh );
  }


  fluent_layouts.fetch_layout_on_refresh = function()
  {
    var layout_selector = $("#id_layout");

    // Firefox will restore form values at refresh.
    // In case this happens, fetch the newly selected layout
    var selected_layout_id = layout_selector.val() || 0;
    var initial_layout_id = layout_selector.attr('data-original-value');
    if( selected_layout_id != initial_layout_id )
    {
      fluent_contents.tabs.hide();
      layout_selector.change();
      return true;
    }

    return false;
  }


  /**
   * If a selectbox has only one choice, enable it.
   */
  fluent_layouts._select_single_option = function(selectbox)
  {
    var options = selectbox[0].options;
    if( ( options.length == 1 )
     || ( options.length == 2 && options[0].value == "" ) )
    {
      selectbox.val( options[ options.length - 1 ].value );
    }
  }


  /**
   * The layout has changed.
   */
  fluent_layouts.onLayoutChange = function(event)
  {
    // TODO: Avoid accessing direct API, have a proper documented external interface.

    var layout_id = this.value;
    if( ! layout_id )
    {
      fluent_contents.tabs.hide(true);
      return;
    }

    // Disable content
    fluent_contents.layout.expire();

    if( event.originalEvent )
    {
      // Real change event, no manual invocation made above
      fluent_contents.tabs.show(true);
    }

    fluent_layouts.fetch_layout(layout_id);
  }


  fluent_layouts.fetch_layout = function(layout_id)
  {
    // Get layout info.
    $.ajax({
      url: ajax_root + "get_layout/" + parseInt(layout_id) + "/?ct_id=" + parseInt(fluent_layouts.ct_id),
      success: function(layout, textStatus, xhr)
      {
        // Ask to update the tabs!
        fluent_contents.layout.load(layout);
      },
      dataType: 'json',
      error: function(xhr, textStatus, ex)
      {
        alert("Internal CMS error: failed to fetch layout data!");    // can't yet rely on $.ajaxError
      }
    })
  }

})(window.jQuery || django.jQuery);
