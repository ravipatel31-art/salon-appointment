import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

/// Portrait bytes served for demo barber photos in widget tests: a valid
/// 1×1 RGBA PNG (brand gold) so [NetworkImage] loads succeed and decode.
const String _kPortraitPngBase64 =
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGPY0Bv+HwAGGQKUTvp+eAAAAABJRU5ErkJggg==';

final Uint8List _portraitPng = base64Decode(_kPortraitPngBase64);

/// Installs an [HttpClient] for widget tests (per flutter_test's HTTP warning:
/// "provide your own HttpClient implementation to the code under test").
///
/// Phase-12 mock barbers ship demo `photo_url`s on `i.pravatar.cc`. The default
/// test client answers every request with an empty HTTP 400, and an offstage
/// `TickerMode` branch stops `Image` error listeners mid-load
/// (`Image.didChangeDependencies`), so those failures surface as unhandled
/// `FlutterError`s the moment a tab switches. This override keeps the demo
/// portraits loading cleanly:
///
/// * `i.pravatar.cc` demo portraits → 200 + tiny valid PNG (loads succeed;
///   no error path, no unhandled `FlutterError` on tab switches).
/// * Any other URL (including the deliberate `broken` fallback fixture) →
///   empty 400, exactly like the default test client, so `errorBuilder`
///   fallback tests keep exercising contract § Imagery.
///
/// Implemented via the `HttpOverrides.global` setter + `HttpOverrides.current`
/// (not `debugNetworkImageHttpClientProvider`) because flutter_test verifies
/// painting debug variables unset *before* package:test `tearDown` hooks run.
/// Dio is unaffected: it creates its own client per request and only ever
/// calls non-portrait URLs → empty 400, same as the default mock.
///
/// Pair [installFakePortraitHttp] (setUp) with [uninstallFakePortraitHttp]
/// (tearDown) so each test restores the binding's original overrides.
void installFakePortraitHttp() {
  _savedHttpOverrides = HttpOverrides.current;
  HttpOverrides.global = _PortraitHttpOverrides();
}

/// Restores the [HttpOverrides] captured by [installFakePortraitHttp].
void uninstallFakePortraitHttp() {
  HttpOverrides.global = _savedHttpOverrides;
  _savedHttpOverrides = null;
}

HttpOverrides? _savedHttpOverrides;

bool _isDemoPortrait(Uri url) =>
    url.toString().contains('i.pravatar.cc') &&
    !url.toString().contains('broken');

class _PortraitHttpOverrides extends HttpOverrides {
  @override
  HttpClient createHttpClient(SecurityContext? context) =>
      _PortraitHttpClient();
}

/// Full [HttpClient] mock: `NetworkImage` does
/// `HttpClient()..autoUncompress = false`, and dio's IOHttpClientAdapter sets
/// `idleTimeout`/`connectionTimeout` and calls `openUrl`/`close` — so every
/// member either frame touches must be real (no throwing `noSuchMethod`).
/// URL methods hand back [_PortraitRequest], whose [HttpClientResponse.close]
/// is portrait-aware (200 + PNG) or empty 400 like flutter_test's mock.
class _PortraitHttpClient implements HttpClient {
  @override
  bool autoUncompress = true;

  @override
  Duration? connectionTimeout;

  @override
  Duration idleTimeout = const Duration(seconds: 15);

  @override
  int? maxConnectionsPerHost;

  @override
  String? userAgent;

  @override
  String Function(Uri url)? findProxy;

  @override
  Future<bool> Function(Uri url, String scheme, String? realm)? authenticate;

  @override
  Future<bool> Function(String host, int port, String scheme, String? realm)?
  authenticateProxy;

  @override
  bool Function(X509Certificate cert, String host, int port)?
  badCertificateCallback;

  @override
  Future<ConnectionTask<Socket>> Function(
    Uri url,
    String? proxyHost,
    int? proxyPort,
  )?
  connectionFactory;

  @override
  void Function(String line)? keyLog;

  @override
  void addCredentials(
    Uri url,
    String realm,
    HttpClientCredentials credentials,
  ) {}

  @override
  void addProxyCredentials(
    String host,
    int port,
    String realm,
    HttpClientCredentials credentials,
  ) {}

  @override
  void close({bool force = false}) {}

  @override
  Future<HttpClientRequest> getUrl(Uri url) async => _PortraitRequest(url);

  @override
  Future<HttpClientRequest> openUrl(String method, Uri url) async =>
      _PortraitRequest(url);

  @override
  Future<HttpClientRequest> headUrl(Uri url) async => _PortraitRequest(url);

  @override
  Future<HttpClientRequest> deleteUrl(Uri url) async => _PortraitRequest(url);

  @override
  Future<HttpClientRequest> patchUrl(Uri url) async => _PortraitRequest(url);

  @override
  Future<HttpClientRequest> postUrl(Uri url) async => _PortraitRequest(url);

  @override
  Future<HttpClientRequest> putUrl(Uri url) async => _PortraitRequest(url);

  @override
  Future<HttpClientRequest> get(String host, int port, String path) async =>
      _PortraitRequest(_hostUri(host, port, path));

  @override
  Future<HttpClientRequest> head(String host, int port, String path) async =>
      _PortraitRequest(_hostUri(host, port, path));

  @override
  Future<HttpClientRequest> delete(String host, int port, String path) async =>
      _PortraitRequest(_hostUri(host, port, path));

  @override
  Future<HttpClientRequest> patch(String host, int port, String path) async =>
      _PortraitRequest(_hostUri(host, port, path));

  @override
  Future<HttpClientRequest> post(String host, int port, String path) async =>
      _PortraitRequest(_hostUri(host, port, path));

  @override
  Future<HttpClientRequest> put(String host, int port, String path) async =>
      _PortraitRequest(_hostUri(host, port, path));

  @override
  Future<HttpClientRequest> open(
    String method,
    String host,
    int port,
    String path,
  ) async => _PortraitRequest(_hostUri(host, port, path));

  static Uri _hostUri(String host, int port, String path) =>
      Uri(scheme: 'http', host: host, port: port, path: path);
}

class _PortraitRequest implements HttpClientRequest {
  _PortraitRequest(this.uri);

  @override
  final Uri uri;

  @override
  final HttpHeaders headers = _PortraitHeaders();

  @override
  int contentLength = -1;

  @override
  bool bufferOutput = true;

  @override
  bool followRedirects = true;

  @override
  int maxRedirects = 5;

  @override
  bool persistentConnection = true;

  @override
  late Encoding encoding;

  @override
  String get method => 'GET';

  @override
  HttpConnectionInfo? get connectionInfo => null;

  @override
  List<Cookie> get cookies => <Cookie>[];

  @override
  Future<HttpClientResponse> get done async => _PortraitResponse(uri);

  @override
  Future<HttpClientResponse> close() async => _PortraitResponse(uri);

  @override
  void add(List<int> data) {}

  @override
  void addError(Object error, [StackTrace? stackTrace]) {}

  @override
  Future<void> addStream(Stream<List<int>> stream) => stream.drain<void>();

  @override
  void abort([Object? exception, StackTrace? stackTrace]) {}

  @override
  Future<void> flush() async {}

  @override
  void write(Object? object) {}

  @override
  void writeAll(Iterable<dynamic> objects, [String separator = '']) {}

  @override
  void writeCharCode(int charCode) {}

  @override
  void writeln([Object? object = '']) {}

  @override
  dynamic noSuchMethod(Invocation invocation) => throw UnsupportedError(
    'test portrait HttpClientRequest has no member `${invocation.memberName}`',
  );
}

class _PortraitResponse extends Stream<List<int>>
    implements HttpClientResponse {
  _PortraitResponse(Uri url)
    : statusCode = _isDemoPortrait(url) ? HttpStatus.ok : HttpStatus.badRequest,
      _body = _isDemoPortrait(url) ? _portraitPng : Uint8List(0);

  @override
  final int statusCode;

  final Uint8List _body;

  @override
  int get contentLength => _body.length;

  @override
  HttpClientResponseCompressionState get compressionState =>
      HttpClientResponseCompressionState.notCompressed;

  @override
  final HttpHeaders headers = _PortraitHeaders();

  @override
  String get reasonPhrase => statusCode == HttpStatus.ok ? 'OK' : 'Bad Request';

  @override
  bool get isRedirect => false;

  @override
  bool get persistentConnection => false;

  @override
  List<Cookie> get cookies => <Cookie>[];

  @override
  List<RedirectInfo> get redirects => <RedirectInfo>[];

  @override
  X509Certificate? get certificate => null;

  @override
  HttpConnectionInfo? get connectionInfo => null;

  @override
  Future<Socket> detachSocket() =>
      Future<Socket>.error(UnsupportedError('test portrait response'));

  @override
  Future<HttpClientResponse> redirect([
    String? method,
    Uri? url,
    bool? followLoops,
  ]) => Future<HttpClientResponse>.error(
    UnsupportedError('test portrait response'),
  );

  @override
  StreamSubscription<List<int>> listen(
    void Function(List<int> event)? onData, {
    Function? onError,
    void Function()? onDone,
    bool? cancelOnError,
  }) {
    return Stream<List<int>>.fromIterable(
      _body.isEmpty ? const <List<int>>[] : <List<int>>[_body],
    ).listen(
      onData,
      onError: onError,
      onDone: onDone,
      cancelOnError: cancelOnError,
    );
  }

  @override
  dynamic noSuchMethod(Invocation invocation) => throw UnsupportedError(
    'test portrait HttpClientResponse has no member `${invocation.memberName}`',
  );
}

class _PortraitHeaders implements HttpHeaders {
  @override
  dynamic noSuchMethod(Invocation invocation) => null;
}
