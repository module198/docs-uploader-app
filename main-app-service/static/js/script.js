$(document).ready(function(){
    $('.form-wrapper, html').addClass('dark');
    $('input[value="dark"]').attr('checked', 'checked');

    $('#options input').click(function(){
        $('.form-wrapper, html')
            .removeClass('dark light none')
            .addClass($(this).val());
    });

    /* Label click for iPad iOS */
    if (navigator.userAgent.match(/iPhone/i) || navigator.userAgent.match(/iPod/i) || navigator.userAgent.match(/iPad/i)) {
        $('label[for]').click(function() {
            var el = $(this).attr('for');
            if ($('#' + el + '[type=radio], #' + el + '[type=checkbox]').attr('selected', !$('#' + el).attr('selected'))) {
                return;
            } else {
                $('#' + el)[0].focus();
            }
        });
    }
});