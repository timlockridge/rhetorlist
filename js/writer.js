/**
* writer.js - Get rdf feeds and write to html
* author: chris lindgren
* notes:
    - buggy, i.e., could use some error handling
    - could also handle incoming rdf data better
    - formatting is drafty too.
*/
var completeList = {};
var requestURLs = [];
var jsonFeed = { articles: [] };

(async () => {
  await rdfRequestLister();
  await rdfFeedParser(requestURLs)
})()

async function rdfRequestLister(){
  return new Promise(function(resolve, reject){
    requestURLs = [
      'https://journals.sagepub.com/action/showFeed?ui=0&mi=ehikzz&ai=2b4&jc=jbtb&type=etoc&feed=rss',//JBTC
      'https://journals.sagepub.com/action/showFeed?ui=0&mi=ehikzz&ai=2b4&jc=jtwa&type=etoc&feed=rss',//JWTC
      'https://journals.sagepub.com/action/showFeed?ui=0&mi=ehikzz&ai=2b4&jc=wcxa&type=etoc&feed=rss',//WritComm
      'https://www.tandfonline.com/action/showFeed?type=etoc&feed=rss&jc=htcq20',//TCQ
      'https://www.tandfonline.com/action/showFeed?type=etoc&feed=rss&jc=hrhr20',//Rhetoric Review
      'https://www.tandfonline.com/action/showFeed?type=etoc&feed=rss&jc=rrsq20'//RSQ
    ];
    resolve("Saved the req urls as an array.");
  })
}

async function rdfFeedParser(rURLs) {
  return new Promise(function(resolve, reject){
    var scopedURLs = rURLs;
    var newFeed = {};

    function parseIt(rURL) {
      // Create RDF object
      var myRDF = new RDF();
      var ns = "http://purl.org/dc/elements/1.1/item/";

      // Get rdf
      myRDF.getRDFURL(rURL, callback);

      function callback() {
        var parsedArticle = {};

        function writeToIndex(art) {
          var pOpen = "<p>", pClose = "</p>";

          function citeAuthors(aSet) {
            if (aSet.length == 1) {
              return aSet;
            }
            if (aSet.length == 2) {
              return aSet[0]+' and '+aSet[1];
            }
            if (aSet.length == 3) {
              return aSet[0]
                  +', '+aSet[1]
                  +', and '+aSet[2];
            }
            if (aSet.length == 4) {
              return aSet[0]
                  +', '+aSet[1]
                  +', '+aSet[2]
                  +', and '+aSet[3];
            }
            if (aSet.length == 5) {
              return aSet[0]
                  +', '+aSet[1]
                  +', '+aSet[2]
                  +', '+aSet[3]
                  +', and '+aSet[4];
            }
          }

          function aheadOfPrint(aop) {
            var ahdData = pOpen
                + citeAuthors(aop.authors)
                + ". (" + aop.date.slice(0,7) + "). "
                + "<cite>"+aop.title+"</cite>. "
                + "Ahead of Print. "
                + "<a href=\""+aop.url+"\" target=\"_blank\" rel=\"noopenner\">"
                + aop.doi+"</a>"
                + pClose;
            return ahdData;
          }

          function published(pa) {
            var pData = pOpen
                + citeAuthors(pa.authors)
                + ". (" + pa.date.slice(0,7) + "). "
                + "<cite>"+pa.title+"</cite>, "
                + pa.vol+"("+pa.issue+"), "
                + pa.spg+"-"+pa.epg
                + ". <a href=\""+pa.url+"\" target=\"_blank\" rel=\"noopenner\">"
                + pa.doi+"</a>"
                + pClose;
            return pData;
          }

          if (art.title !== "Manuscript Reviewers" || art.title !== "Reviewers" || art.title !== "Editor’s Message") {
            if (art.vol === null) {

              if (art.journal == "Written Communication") {
                var section = document.getElementById('articles-wc');
                var wcArticle = aheadOfPrint(art);
                section.insertAdjacentHTML('beforeend', wcArticle);
              }
              else if (art.journal == "Rhetoric Review") {
                var section = document.getElementById('articles-rr');
                var rrArticle = aheadOfPrint(art);
                section.insertAdjacentHTML('beforeend', rrArticle);
              }
              else if (art.journal == "Rhetoric Society Quarterly") {
                var section = document.getElementById('articles-rsq');
                var rsqArticle = aheadOfPrint(art);
                section.insertAdjacentHTML('beforeend', rsqArticle);
              }
              else if (art.journal == "Technical Communication Quarterly") {
                var section = document.getElementById('articles-tcq');
                var tcqArticle = aheadOfPrint(art);
                section.insertAdjacentHTML('beforeend', tcqArticle);
              }
              else if (art.journal == "Journal of Technical Writing and Communication") {
                var section = document.getElementById('articles-jtwc');
                var jtwcArticle = aheadOfPrint(art);
                section.insertAdjacentHTML('beforeend', jtwcArticle);
              }
              else if (art.journal == "Journal of Business and Technical Communication") {
                var section = document.getElementById('articles-jbtc');
                var jbtcArticle = aheadOfPrint(art);
                section.insertAdjacentHTML('beforeend', jbtcArticle);
              }

            }
            else if (art.vol !== null) {

              if (art.journal == "Written Communication") {
                var section = document.getElementById('articles-wc');
                var wcArticle = published(art);
                section.insertAdjacentHTML('beforeend', wcArticle);
              }
              else if (art.journal == "Rhetoric Review") {
                var section = document.getElementById('articles-rr');
                var rrArticle = published(art);
                section.insertAdjacentHTML('beforeend', rrArticle);
              }
              else if (art.journal == "Rhetoric Society Quarterly") {
                var section = document.getElementById('articles-rsq');
                var rsqArticle = published(art);
                section.insertAdjacentHTML('beforeend', rsqArticle);
              }
              else if (art.journal == "Technical Communication Quarterly") {
                var section = document.getElementById('articles-tcq');
                var tcqArticle = published(art);
                section.insertAdjacentHTML('beforeend', tcqArticle);
              }
              else if (art.journal == "Journal of Technical Writing and Communication") {
                var section = document.getElementById('articles-jtwc');
                var jtwcArticle = published(art);
                section.insertAdjacentHTML('beforeend', jtwcArticle);
              }
              else if (art.journal == "Journal of Business and Technical Communication") {
                var section = document.getElementById('articles-jbtc');
                var jbtcArticle = published(art);
                section.insertAdjacentHTML('beforeend', jbtcArticle);
              }

            }
            resolve(console.log("Finished writing a URL."));
          }
      }

        function getAuthors(s) {
          var authsReturned = [];
          var listAuthors = myRDF.Match(null, s, "http://purl.org/dc/elements/1.1/creator", null);

          for (var ar = 0; ar <= listAuthors.length-1; ar++) {
            authsReturned.push(listAuthors[ar].object);
          }

          return authsReturned;
        }

        function retrieveArticleURL(si) {
          // NOTE: Using si.length-2, due to unwanted meta tag
          for (var r = 0; r <= si.length-2; r++) {
            var skipSeq = r + 1;
            var subject = myRDF.getSingleObject(null, "genid:2", "http://www.w3.org/1999/02/22-rdf-syntax-ns#_"+skipSeq, null);
            parsedArticle = {
              title: myRDF.getSingleObject(null, subject, "http://purl.org/rss/1.0/title", null),
              url: myRDF.getSingleObject(null, subject, "http://purl.org/rss/1.0/link", null),
              doi: myRDF.getSingleObject(null, subject, "http://purl.org/dc/elements/1.1/identifier", null),
              date: myRDF.getSingleObject(null, subject, "http://purl.org/dc/elements/1.1/date", null),
              journal: myRDF.getSingleObject(null, subject, "http://purl.org/dc/elements/1.1/source", null),
              vol: myRDF.getSingleObject(null, subject, "http://prismstandard.org/namespaces/basic/2.0/volume", null),
              issue: myRDF.getSingleObject(null, subject, "http://prismstandard.org/namespaces/basic/2.0/number", null),
              spg: myRDF.getSingleObject(null, subject, "http://prismstandard.org/namespaces/basic/2.0/startingPage", null),
              epg: myRDF.getSingleObject(null, subject, "http://prismstandard.org/namespaces/basic/2.0/endingPage", null),
              authors: getAuthors(subject)
            };
            writeToIndex(parsedArticle);
          }

        }
        var seqItems = myRDF.Match(null, "genid:2", null, null);
        retrieveArticleURL(seqItems);
      }
    }

    for (var ri = 0; ri <= scopedURLs.length-1; ri++) {
      parseIt(scopedURLs[ri]);
    }
  })
}
