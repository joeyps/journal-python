Object.size = function(obj) {
    var size = 0, key;
    for (key in obj) {
        if (obj.hasOwnProperty(key)) size++;
    }
    return size;
};

Object.toArray = function(obj) {
	var ary = [];
    for (key in obj) {
        if (obj.hasOwnProperty(key)) ary.push(obj[key]);
    }
	return ary;
};

Date.prototype.addHours= function(h){
    this.setHours(this.getHours()+h);
    return this;
};

if (!String.prototype.format) {
	String.prototype.format = function() {
		var args = arguments;
		return this.replace(/{(\d+)}/g, function(match, number) { 
			return typeof args[number] != 'undefined'
				? args[number]
				: match;
			});
	};
}

core = {
	DATE_FORMAT:"yyyy-mm-dd",
	DATETIME_FORMAT:"yyyy-mm-dd hh:MM:ss",
	timezone:(-new Date().getTimezoneOffset()/60),
	events: {
		bind:function(obj, type, callback) {
			if (!obj.event) {
				obj.event = {};
			}
			obj.event[type] = callback;
		},
		unbind:function(obj, type) {
			if (!obj.event) {
				obj.event = {};
			} else {
				obj.event[type] = null;
			}
		},
		trigger:function(obj, type, args) {
			if (!obj.event) {
				obj.event = {};
			} else {
				var cb = obj.event[type];
				if (cb) {
					cb(args);
				}
			}
		}
	}
};

core.api = function() {
	if(arguments.length < 2) {
		return;
	}

	var args = Array.prototype.slice.call(arguments);

	var path = "/_api" + args[0];
	var method = args[1];

	var opt_argv = args.slice(2, args.length);

    if (!opt_argv)
    opt_argv = new Array();

    // Find if the last arg is a callback function; save it
    var callback = null;
    var len = opt_argv.length;
    if (len > 0 && typeof opt_argv[len-1] === 'function') {
        callback = opt_argv[len-1];
        opt_argv.length--;
    }

	var params = null;
	if(opt_argv.length > 0) {
		params = opt_argv[0]
	}

	var opts = {
		url:path,
		type:method
	}

	if(params != null) {
		opts['data'] = { data:JSON.stringify(params) };
	}

	var that = this;
	$.ajax(opts).done(function(response) {
		var res = JSON.parse(response);
		if(callback) {
			callback(res);
		}
	}).fail(function(jqxhr, textStatus, errorThrown) {

	});
};

function Jourmap() {
	var me = this;
	me.DATE_FORMAT = "yyyy-mm-dd";
	me.utils = {
		timezone:(-new Date().getTimezoneOffset()/60),
		current_time:function(time) {
			time.addHours(JM.utils.timezone);
			return time;
		}
	};
}

JM = new Jourmap();

function Menu(selector, options) {
	var m = this;
	m.menu = $(selector)
	m.options = options;
	m.menu.find('.menuitem').click(function() {
		var action = $(this).attr('act');
		options.select['action']();
	});
}

Menu.prototype.show = function() {
	this.menu.show();
};

Menu.prototype.hide = function() {
	this.menu.hide();
};

function strptime(str) {
	var datetime = str.split(' ');
	var date = datetime[0];
	var time = datetime[1];
	var dateParts = date.split('-');
	var timeParts = time.split(':');
	return new Date(dateParts[0], dateParts[1] - 1, dateParts[2], timeParts[0], timeParts[1], timeParts[2]);
}

function strpdate(str) {
	var dateParts = str.split('-');
	return new Date(dateParts[0], dateParts[1] - 1, dateParts[2]);
}

function parseDomain(url) {
	var matches = /\/\/([^\/]+)/.exec(url);
	if(matches)
		return matches[1];
	return null;
}

URLShortener = {
	api:"https://www.googleapis.com/urlshortener/v1/url",
	key:"AIzaSyBUqMyu_SCiFkrgyeVg41hUdQvmnY3_MtA",
	post:function(url, callback) {
		$.ajax({
			url:URLShortener.api + (URLShortener.key ? ("?key=" + URLShortener.key) : ""),
			type:"POST",
			contentType:"application/json",
			data: JSON.stringify({
				longUrl:url
			}),
			processData: false
		}).done(function(res) {
			callback(res);
		});
	},
	analytics:function(shorten_url, callback) {
		$.ajax({
			url:"https://www.googleapis.com/urlshortener/v1/url?shortUrl=" + shorten_url + "&projection=FULL" + (URLShortener.key ? ("&key=" + URLShortener.key) : ""),
		}).done(function(res) {
			callback(res);
		});
	}
}

//cc
function CommentsHandler(container, urlPostTo) {
	var me = this;
	this.container = container;
	this.urlPostTo = urlPostTo;
	this.next_curs = null;
	this.viewHistory = this.container.find(".history");
	this.viewMore = container.find(".more").click(function() {
		me.fetch();
	});

	var me = this;
	var btnPost = container.find(".comment-new .btn-post");
	btnPost.click(function() {
		var content = container.find(".comment-new .editable").html();
		if(content.trim() != "") {
			JM.api(me.urlPostTo, "POST", { content:content }, function(res) {
				if(res) {
					me.viewHistory.append(me._inflateComment(res));
				}
			});
		}
		container.find(".comment-new .btn-cancel").trigger('click');
	});
	container.find(".comment-new .editable").keyup(function() {
		if($(this).html().trim().length <= 0)
			btnPost.attr("disabled", "disabled");
		else
			btnPost.removeAttr("disabled");
	});
	
	container.find(".placeholder").click(function() {
		$(this).hide();
		container.find(".comment-new .editable").html("").trigger('keyup');
		container.find(".comment-new").show();
		container.find(".comment-new .editable").focus();
	});
	
	container.find(".comment-new .btn-cancel").click(function() {
		container.find(".comment-new").hide();
		container.find(".comment-new .editable").html("");
		container.find(".placeholder").show();
	});
}

CommentsHandler.prototype.clear = function() {
	var me = this;
	me.container.find(".history").html("");
	me.next_curs = null;
	me.viewMore.hide();
};

CommentsHandler.prototype.fetch = function() {
	var me = this;
	var url = me.urlPostTo + (me.next_curs ? "?cursor=" + me.next_curs : "");
	JM.api(url, "GET", function(res) {
		if(res) {
			me.next_curs = res.next_curs;
			if(res.more)
				me.viewMore.show();
			else
				me.viewMore.hide();
			for(var i in res.comments) {
				me.viewHistory.prepend(me._inflateComment(res.comments[i]));
			}
		}
	});
};

CommentsHandler.prototype._inflateComment = function(comment) {
	var html = '<div class="comment">' + 
		'<a href="/u/' + comment.owner.id +'">' + 
			'<img class="profile-picture" src="' + comment.owner.profile_picture +'" />' + 
		'</a>' +
		'<div class="comment-content">' + 
			'<span>' +
				'<a class="name" href="/u/' + comment.owner.id +'">' + comment.owner.name +'</a>' + 
				'&nbsp;&nbsp;' + 
				'<span class="time txt2nd" time="' + comment.created_time +'">' + 
				format_time(strptime(comment.created_time, JM.utils.timezone)) + '</span>' + 
			'</span>' + 
			'<div class="body">' + 
				 comment.content +
			'</div>' + 
		'</div>' +
	'</div>';
	return $(html);
};

function Alarm(onAlarm) {
	this.onAlarm = onAlarm;
	this.interval = 0;
	this.timeout = null;
}

Alarm.prototype.start = function(interval) {
	this.timeout = setTimeout(this.onAlarm, interval);
};

Alarm.prototype.cancel = function() {
	if(this.timeout != null) {
		clearTimeout(this.timeout);
		this.timeout = null;
	}
};

function strptime(str, offset) {
	if (typeof offset === 'undefined')
		offset = 0;
	var datetime = str.split(' ');
	var date = datetime[0];
	var time = datetime[1];
	var dateParts = date.split('-');
	var timeParts = time.split(':');
	return new Date(dateParts[0], dateParts[1] - 1, dateParts[2], timeParts[0], timeParts[1], timeParts[2]).addHours(offset);
}

function strpdate(str) {
	var dateParts = str.split('-');
	return new Date(dateParts[0], dateParts[1] - 1, dateParts[2]);
}

function format_time(time, from_now) {
    if(!time)
        return null;
    var now = new Date();
    var target = time;
    var diff = now - target
	if (typeof from_now === 'undefined')
		from_now = true;
	var days = Math.floor(diff / 24.0 / 60.0 / 60.0 / 1000.0);
    if (from_now && days ==0) {
        var seconds = Math.floor(diff / 1000.0);
        var hours = Math.floor(seconds / 60.0 / 60.0);
        if (hours > 0) {
            return "{0} hr{1}".format(hours, hours > 1 ? "s" : "")
        } else {
            var mins = Math.floor(seconds / 60.0);
            if (mins > 0) {
                return "{0} min{1}".format(mins, mins > 1 ? "s" : "")
            } else {
                return "Just now";
			}
		}
	} else if (from_now && days == 1) {
        return "Yesterday";
    } else if (from_now && days >= 2 && days <=3) {
        return days + " days ago";
    } else {
        return time.format("mmm") + " " + time.getDate();
	}
}

function UploadManager(opts) {
	this.opts = opts;
	this.onStart = opts.onStart;
	this.done = opts.done;
	this.progress = opts.progress;
	this.current = 0;
	this.num_uploaded = 0;
	this.num_failed = 0;
	this.isuploading = false;
}

UploadManager.prototype.start = function(files, to) {
	var um = this;
	if(um.isuploading || files.length <= 0)
		return;
	um.isuploading = true;
	um.current = 0;
	um.files = files;
	um.num_uploaded = 0;
	um.num_failed = 0;
	um.total_size = um.files.length * 100;
	um.uploaded_size = 0;
	um.progress(files[0], um.current, um.files.length, 0);
	um.onStart();
	
	function next() {
		um.current++;
		if(um.current < um.files.length) {
			upload(files[um.current]);
		} else {
			um.isuploading = false;
			um.done();
		}
	}
	
	function upload(file) {
		var name = file.name;
	    if(file.size > 100000000) {
			//up to 100MB
	        //alert("File is to big");
			um.num_failed++;
			next();
	    }
	    else if(!file.type.match(/image.*/)) {
	        //alert("File doesnt match png, jpg or gif");
			um.num_failed++;
			next();
	    }
	    else { 
            var formData = new FormData();
			formData.append("files", file);
            $.ajax({
                url: to,  //server script to process data
                type: 'POST',
                xhr: function() {  // custom xhr
                    var xhr = $.ajaxSettings.xhr();
					xhr.addEventListener('progress', function(e) {
				        var done = e.position || e.loaded, total = e.totalSize || e.total;
				    }, false);
				    if ( xhr.upload ) {
				        xhr.upload.onprogress = function(e) {
				            var done = e.position || e.loaded, total = e.totalSize || e.total;
							var progress = Math.floor(done/total*100);
							um.opts.fileprogress(um.current, file, progress);
							um.progress(file, um.num_uploaded, um.files.length, ((um.num_uploaded * 100.0 + progress) / um.total_size) * 100);
				        };
				    }
                    return xhr;
                },
                // Form data
                data: formData,
                //Options to tell JQuery not to process data or worry about content-type
                cache: false,
                contentType: false,
                processData: false
            })
			.done(function(response){ 
				response = JSON.parse(response);
				um.num_uploaded++;
				um.progress(file, um.num_uploaded, um.files.length, (um.num_uploaded * 100.0 / um.total_size) * 100);
				um.opts.uploaded(um.current, file, response);
				next();
			})
			.fail(function(jqxhr, textStatus, errorThrown) { 
				um.num_failed++;
				next();
			});
	    }
	}
	
	upload(um.files[um.current]);
	
};